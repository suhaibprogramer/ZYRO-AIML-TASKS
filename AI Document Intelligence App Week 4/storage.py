"""
File storage (Week 4, Task 1/3/8).

- Validates uploads (type, size, real file content)
- Hashes files with SHA-256 (for duplicate detection)
- Saves files in storage/invoices, storage/resumes or storage/other
  using SAFE generated filenames (the original name is kept in the database only)
"""

import hashlib
import logging
import os
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
STORAGE_ROOT = BASE_DIR / "storage"          # tests may change this

ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}
MAX_UPLOAD_MB = 10
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

FOLDER_FOR_TYPE = {"Invoice": "invoices", "Resume": "resumes", "Other": "other"}

# First bytes of a real file of each type
SIGNATURES = {
    "pdf": [b"%PDF"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
}


def get_extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def validate_upload(filename: str, data: bytes) -> tuple[bool, str]:
    """Returns (ok, friendly_message). Checks type, emptiness, size and file content."""
    ext = get_extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        return False, "This file type is not supported. Please upload a PDF, JPG, JPEG or PNG file."
    if len(data) == 0:
        return False, "This file is empty."
    if len(data) > MAX_UPLOAD_BYTES:
        return False, f"This file is too large. The limit is {MAX_UPLOAD_MB} MB."
    if not any(data.startswith(sig) for sig in SIGNATURES[ext]):
        return False, "The file content does not match its extension. It may be damaged or renamed."
    return True, ""


def compute_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_stored_filename(doc_type: str, file_hash: str, ext: str) -> str:
    """Safe filename: type + short hash + random id. Never uses the uploaded name."""
    ext = "jpg" if ext == "jpeg" else ext
    return f"{doc_type.lower()}_{file_hash[:8]}_{uuid.uuid4().hex[:8]}.{ext}"


def save_file(data: bytes, doc_type: str, file_hash: str, ext: str) -> tuple[str, str]:
    """Saves the file. Returns (stored_filename, file_path) - path is relative to the project."""
    folder = FOLDER_FOR_TYPE.get(doc_type, "other")
    target_dir = STORAGE_ROOT / folder
    target_dir.mkdir(parents=True, exist_ok=True)

    stored_filename = make_stored_filename(doc_type, file_hash, ext)
    full_path = target_dir / stored_filename
    with open(full_path, "wb") as f:
        f.write(data)

    relative = Path(os.path.relpath(full_path, STORAGE_ROOT.parent)).as_posix()
    return stored_filename, relative


def absolute_path(file_path: str) -> Path:
    return STORAGE_ROOT.parent / file_path


def read_file(file_path: str) -> bytes | None:
    """Returns the file's bytes, or None if it is missing."""
    try:
        return absolute_path(file_path).read_bytes()
    except OSError:
        return None


def delete_file(file_path: str) -> None:
    try:
        absolute_path(file_path).unlink(missing_ok=True)
    except OSError:
        logger.exception("Could not delete file")
