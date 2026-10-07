"""Pipeline glue: Upload -> Process -> Classify -> Extract -> Validate ->
Apply Rules -> Review / Approve / Reject -> Complete -> Audit.

No Streamlit code here, so it can be tested directly.
"""
import time
from dataclasses import dataclass
from typing import Optional

import audit
import classifier
import database as db
import extractor
import processor
import storage
import validator
import workflow as wf


@dataclass
class UploadResult:
    ok: bool
    message: str
    doc_id: Optional[int] = None
    duplicate_of: Optional[int] = None


def ingest(filename: str, data: bytes, db_path=None, storage_root=None) -> UploadResult:
    """Validate, de-duplicate and store a file; create the document in state New."""
    try:
        storage.validate_upload(filename, data)
        file_hash = storage.sha256_bytes(data)
        existing = db.find_by_hash(file_hash, db_path)
        if existing:
            audit.log_event(existing["id"], "Duplicate upload blocked", existing["status"],
                            existing["status"], f"Re-upload of '{filename}'", db_path)
            return UploadResult(False, f"Duplicate: this file is already stored as '{existing['filename']}' "
                                       f"(ID {existing['id']}).", existing["id"], existing["id"])
        path = storage.save_file(filename, data, root=storage_root)
        try:
            doc_id = db.insert_document(filename, path, file_hash, len(data), db_path)
        except db.DatabaseError:
            _remove_quietly(path)  # don't leave an orphan file if the DB write failed
            raise
        audit.log_event(doc_id, "Uploaded", None, wf.NEW, f"File '{filename}' stored", db_path)
        return UploadResult(True, "Uploaded.", doc_id)
    except (storage.StorageError, db.DatabaseError) as exc:
        return UploadResult(False, str(exc))


def _remove_quietly(path):
    import os
    try:
        os.remove(path)
    except OSError:
        pass


def run_workflow(doc_id: int, db_path=None, storage_root=None) -> dict:
    """Run the full workflow for one document and return a result record.

    Outcome is one of: "processed" (auto-approved and completed),
    "review" (sent to Needs Review) or "failed" (an error; document stays New).
    Never raises - one bad document must not stop a batch.
    """
    result = {"id": doc_id, "filename": None, "outcome": "failed", "status": None, "reason": ""}
    try:
        doc = db.get_document(doc_id, db_path)
        if doc is None:
            result["reason"] = "Document not found."
            return result
        result["filename"] = doc["filename"]
        result["status"] = doc["status"]

        # New -> Processing (blocked if the document is in any other state)
        wf.change_status(doc_id, wf.PROCESSING, "Processing started", db_path=db_path)
        started = time.perf_counter()
        try:
            data = storage.read_file(doc["stored_path"])
            text = processor.extract_text(data, doc["filename"])
            readable = processor.has_readable_text(text)
            doc_type, confidence, clf_name = classifier.classify(text)
            fields = extractor.extract_fields(doc_type, text)
            validation = validator.validate(doc_type, fields)
            decision = wf.decide(doc_type, validation, confidence, readable)
            elapsed_ms = int((time.perf_counter() - started) * 1000)

            new_path = storage.move_to_type_folder(doc["stored_path"], doc_type, storage_root)
            db.update_document(doc_id, db_path, doc_type=doc_type, confidence=confidence,
                               classifier=clf_name, extracted_text=text, fields=fields,
                               validation=validation, processing_ms=elapsed_ms)
            _set_path(doc_id, new_path, db_path)
            audit.log_event(doc_id, "Classified & extracted", wf.PROCESSING, wf.PROCESSING,
                            f"type={doc_type}; classifier={clf_name}; confidence="
                            f"{'n/a' if confidence is None else round(confidence, 3)}", db_path)
            audit.log_event(doc_id, "Validated", wf.PROCESSING, wf.PROCESSING,
                            "valid" if validation["valid"] else
                            f"missing={validation['missing']}; invalid={list(validation['invalid'])}", db_path)

            if decision.next_status == wf.NEEDS_REVIEW:
                wf.change_status(doc_id, wf.NEEDS_REVIEW, decision.action, decision.reason,
                                 review_reason=decision.reason, db_path=db_path)
                result.update(outcome="review", status=wf.NEEDS_REVIEW, reason=decision.reason)
            else:
                wf.change_status(doc_id, wf.APPROVED, decision.action, decision.reason,
                                 review_reason=None, db_path=db_path)
                wf.change_status(doc_id, wf.COMPLETED, "Workflow completed",
                                 "Auto-approved document completed", db_path=db_path)
                result.update(outcome="processed", status=wf.COMPLETED, reason=decision.reason)
        except Exception as exc:  # any processing error: roll back to New so it can be retried
            reason = _safe_message(exc)
            try:
                wf.change_status(doc_id, wf.NEW, "Processing failed", reason, db_path=db_path)
            except Exception:
                pass
            result.update(outcome="failed", status=wf.NEW, reason=reason)
    except wf.InvalidTransition as exc:
        result.update(outcome="failed", reason=str(exc))
    except Exception as exc:  # e.g. database down - report it, never crash
        result.update(outcome="failed", reason=_safe_message(exc))
    return result


def _set_path(doc_id, path, db_path):
    with db.get_conn(db_path) as conn:
        conn.execute("UPDATE documents SET stored_path=? WHERE id=?", (path, doc_id))


def _safe_message(exc: Exception) -> str:
    """Only show messages from our own error types; hide raw library errors."""
    if isinstance(exc, (processor.ProcessingError, storage.StorageError, db.DatabaseError, wf.InvalidTransition)):
        return str(exc)
    return "Unexpected error while processing this document."


def run_batch(doc_ids, db_path=None, storage_root=None) -> dict:
    """Run the workflow for every id. One failure never stops the batch."""
    results = [run_workflow(i, db_path, storage_root) for i in doc_ids]
    return {
        "results": results,
        "processed": sum(r["outcome"] == "processed" for r in results),
        "review": sum(r["outcome"] == "review" for r in results),
        "failed": sum(r["outcome"] == "failed" for r in results),
    }
