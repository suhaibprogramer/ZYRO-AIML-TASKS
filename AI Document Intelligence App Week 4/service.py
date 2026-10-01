"""
Upload service (Week 4 target flow), with no Streamlit code:

Validate -> Hash -> Duplicate check -> Read/OCR -> Clean -> Classify -> Extract
-> Store file -> Store metadata

ingest_document() never raises. It returns a dict with an "outcome":
  "saved"      - new document stored (see "document")
  "duplicate"  - same file already stored (see "document" = the existing one)
  "rejected"   - file not allowed (see "message")
  "error"      - something failed (see "message", which is safe to show)
"""

import logging
from datetime import datetime

import database as db
import document_processor as dp
import storage

logger = logging.getLogger(__name__)

PREVIEW_CHARS = 500


def _build_record(original_filename, stored_filename, file_path, file_hash, size, result) -> dict:
    f = result["fields"]
    na = dp.NOT_FOUND
    pick = lambda key: (f.get(key) if f.get(key, na) != na else None)

    return {
        "original_filename": original_filename,
        "stored_filename": stored_filename,
        "document_type": result["doc_type"],
        "confidence": result["confidence"],
        "upload_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "company": pick("Company Name"),
        "invoice_number": pick("Invoice Number"),
        "invoice_date": pick("Date"),
        "total_amount": pick("Total Amount"),
        "person_name": pick("Name"),
        "email": pick("Email"),
        "phone": pick("Phone"),
        "skills": pick("Skills"),
        "file_path": file_path,
        "file_size": size,
        "extraction_method": result["method"],
        "text_preview": result["text"][:PREVIEW_CHARS],
        "file_hash": file_hash,
        "status": result["status"],
        "status_note": result["status_note"],
    }


def ingest_document(original_filename: str, data: bytes) -> dict:
    try:
        # 1. Validate
        ok, message = storage.validate_upload(original_filename, data)
        if not ok:
            return {"outcome": "rejected", "message": message}

        # 2. Hash + duplicate check (before doing any slow work)
        file_hash = storage.compute_hash(data)
        existing = db.get_document_by_hash(file_hash)
        if existing:
            return {"outcome": "duplicate", "document": existing}

        # 3. Read / clean / classify / extract / status
        ext = storage.get_extension(original_filename)
        result = dp.process_document(data, ext)

        # 4. Store the file (Failed documents go to "other")
        stored_filename, file_path = storage.save_file(data, result["doc_type"], file_hash, ext)

        # 5. Store metadata
        record = _build_record(original_filename, stored_filename, file_path,
                               file_hash, len(data), result)
        try:
            doc_id = db.insert_document(record)
        except db.DuplicateHashError:
            storage.delete_file(file_path)
            return {"outcome": "duplicate", "document": db.get_document_by_hash(file_hash)}
        except db.DatabaseError:
            storage.delete_file(file_path)     # don't leave an orphan file behind
            raise

        return {"outcome": "saved", "document": db.get_document(doc_id), "result": result}

    except db.DatabaseError as e:
        return {"outcome": "error", "message": str(e)}
    except OSError:
        logger.exception("Could not save file")
        return {"outcome": "error", "message": "The file could not be saved. Please try again."}
    except Exception:
        logger.exception("Unexpected error while ingesting a document")
        return {"outcome": "error", "message": "Something went wrong while handling this file."}
