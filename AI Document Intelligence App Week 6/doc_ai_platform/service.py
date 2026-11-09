"""The integrated pipeline (no UI code, so the Streamlit app, the API and the tests share it).

Upload -> Validate -> OCR/Text -> Classify -> Extract -> Store -> Verify ->
Anomaly check -> AI index -> Workflow decision -> Review/Approve/Reject -> Audit
"""
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Optional

import anomaly
import audit
import classifier
import database as db
import extractor
import processor
import rag
import storage
import validator
import workflow as wf

log = logging.getLogger(__name__)


@dataclass
class UploadResult:
    ok: bool
    message: str
    doc_id: Optional[int] = None
    duplicate_of: Optional[int] = None
    code: Optional[str] = None     # duplicate, unsupported_type, too_large, empty, invalid_content, corrupt, ...


# --------------------------------------------------------------------- upload
def ingest(filename: str, data: bytes) -> UploadResult:
    """Validate, de-duplicate and store a file; create the document in state New.

    Rejected files are never stored; the reason is recorded for the dashboard.
    """
    try:
        storage.validate_upload(filename, data)      # type, size, real content type
        processor.check_integrity(data, filename)     # opens the file: corrupt / encrypted / too big
        file_hash = storage.sha256_bytes(data)
        existing = db.find_by_hash(file_hash)         # same bytes = same document
        if existing:
            audit.log_event(existing["id"], "Duplicate upload blocked", existing["status"],
                            existing["status"], f"Re-upload of '{filename}'")
            return UploadResult(False, f"Duplicate: this file is already stored as '{existing['filename']}' "
                                       f"(ID {existing['id']}).", existing["id"], existing["id"], "duplicate")
        path = storage.save_file(filename, data)
        try:
            doc_id = db.insert_document(filename, path, file_hash, len(data))
        except db.DatabaseError:
            storage.remove_quietly(path)              # never leave an orphan file behind
            raise
        audit.log_event(doc_id, "Uploaded", None, wf.NEW, f"File '{filename}' stored")
        return UploadResult(True, "Uploaded.", doc_id)
    except (storage.StorageError, processor.ProcessingError) as exc:
        _log_rejection(filename, exc.code, str(exc))
        return UploadResult(False, str(exc), code=exc.code)
    except db.DatabaseError as exc:
        return UploadResult(False, str(exc), code="database")


def _log_rejection(filename: str, code: str, reason: str) -> None:
    try:
        db.log_rejection(filename, code, reason)
    except db.DatabaseError:
        pass  # the user still gets the rejection message


# ------------------------------------------------------------------- workflow
@contextmanager
def _stage(timings: dict, name: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        timings[name] = round((time.perf_counter() - start) * 1000, 1)


def run_workflow(doc_id: int) -> dict:
    """Run the full pipeline for one document and return a result record.

    outcome is one of:
      processed  auto-approved and completed
      review     sent to Needs Review (reason says why)
      failed     an error; the document goes back to New so it can be retried
      skipped    already processed - stored results are reused, nothing is recomputed
    Never raises, so one bad document cannot stop a batch.
    """
    result = {"id": doc_id, "filename": None, "outcome": "failed", "status": None, "reason": ""}
    try:
        doc = db.get_document(doc_id)
        if doc is None:
            result["reason"] = "Document not found."
            return result
        result.update(filename=doc["filename"], status=doc["status"])

        if doc["status"] != wf.NEW:  # valid stored results exist: do not reprocess
            audit.log_event(doc_id, "Reprocessing skipped", doc["status"], doc["status"],
                            "Stored results reused")
            result.update(outcome="skipped",
                          reason=f"Already processed (status: {doc['status']}); stored results reused.")
            return result

        wf.change_status(doc_id, wf.PROCESSING, "Processing started")
        timings = {}
        started = time.perf_counter()
        try:
            with _stage(timings, "read_file"):
                data = storage.read_file(doc["stored_path"])
            with _stage(timings, "text_extraction"):
                text, method = processor.read_document(data, doc["filename"])
            readable = processor.has_readable_text(text)
            with _stage(timings, "classification"):
                doc_type, confidence, clf_name = classifier.classify(text)
            with _stage(timings, "field_extraction"):
                fields = extractor.extract_fields(doc_type, text)
            with _stage(timings, "validation"):
                validation = validator.validate(doc_type, fields)
            with _stage(timings, "anomaly_check"):
                anomalies = anomaly.detect(doc_id, doc_type, fields)
            with _stage(timings, "ai_indexing"):
                rag.index_document(doc_id, text if readable else "")
            decision = wf.decide(doc_type, validation, confidence, readable, anomalies)
            timings["total"] = round((time.perf_counter() - started) * 1000, 1)

            new_path = storage.move_to_type_folder(doc["stored_path"], doc_type)
            db.update_document(doc_id, doc_type=doc_type, confidence=confidence, classifier=clf_name,
                               text_method=method, extracted_text=text, fields=fields,
                               validation=validation, anomalies=anomalies, timings=timings,
                               processing_ms=int(timings["total"]), stored_path=new_path)
            conf_txt = "n/a" if confidence is None else f"{confidence:.3f}"
            audit.log_event(doc_id, "Classified & extracted", wf.PROCESSING, wf.PROCESSING,
                            f"type={doc_type}; classifier={clf_name}; confidence={conf_txt}; text via {method}")
            audit.log_event(doc_id, "Validated", wf.PROCESSING, wf.PROCESSING,
                            "all required fields valid" if validation["valid"] else
                            f"missing={validation['missing']}; invalid={list(validation['invalid'])}")
            audit.log_event(doc_id, "Anomaly check", wf.PROCESSING, wf.PROCESSING,
                            "; ".join(a["code"] for a in anomalies) or "no anomalies")

            if decision.next_status == wf.NEEDS_REVIEW:
                wf.change_status(doc_id, wf.NEEDS_REVIEW, decision.action, decision.reason,
                                 review_reason=decision.reason)
                result.update(outcome="review", status=wf.NEEDS_REVIEW, reason=decision.reason)
            else:
                wf.change_status(doc_id, wf.APPROVED, decision.action, decision.reason, review_reason=None)
                wf.change_status(doc_id, wf.COMPLETED, "Workflow completed", "Auto-approved document completed")
                result.update(outcome="processed", status=wf.COMPLETED, reason=decision.reason)
        except Exception as exc:  # any processing error: back to New so it can be retried
            reason = _safe_message(exc)
            log.exception("Processing failed for document %s", doc_id)
            try:
                wf.change_status(doc_id, wf.NEW, "Processing failed", reason)
            except Exception:
                pass
            result.update(outcome="failed", status=wf.NEW, reason=reason)
    except wf.InvalidTransition as exc:
        result.update(outcome="failed", reason=str(exc))
    except Exception as exc:  # e.g. the database is down
        log.exception("Workflow error for document %s", doc_id)
        result.update(outcome="failed", reason=_safe_message(exc))
    return result


_SAFE_ERRORS = (processor.ProcessingError, storage.StorageError, db.DatabaseError, wf.InvalidTransition)


def _safe_message(exc: Exception) -> str:
    """Only our own error messages are shown; raw library errors are hidden (and logged)."""
    if isinstance(exc, _SAFE_ERRORS):
        return str(exc)
    return "Unexpected error while processing this document."


def run_batch(doc_ids) -> dict:
    """Run the workflow for every id. One failure never stops the batch."""
    ids = list(dict.fromkeys(doc_ids))  # drop repeated ids, keep order
    started = time.perf_counter()
    results = [run_workflow(i) for i in ids]
    count = lambda o: sum(r["outcome"] == o for r in results)  # noqa: E731
    return {"results": results, "processed": count("processed"), "review": count("review"),
            "failed": count("failed"), "skipped": count("skipped"),
            "seconds": round(time.perf_counter() - started, 2)}


def upload_and_process(filename: str, data: bytes, process: bool = True) -> dict:
    """Convenience used by the UI and API: ingest, then run the workflow."""
    up = ingest(filename, data)
    wfres = run_workflow(up.doc_id) if (up.ok and process) else None
    return {"upload": up, "workflow": wfres}


def recover_interrupted() -> int:
    """After a crash or restart, documents stuck in 'Processing' go back to 'New' so they can be retried."""
    count = 0
    for doc_id in db.stuck_processing_ids():
        try:
            wf.change_status(doc_id, wf.NEW, "Recovered after restart", "Processing was interrupted")
            count += 1
        except wf.InvalidTransition:
            pass
    return count
