"""File storage and duplicate handling."""
import hashlib
import os
import re
import uuid

STORAGE_ROOT = "storage"
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
TYPE_FOLDERS = {"Invoice": "invoices", "Resume": "resumes"}


class StorageError(Exception):
    """Raised for rejected files or disk problems (message is safe to show)."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_filename(name: str) -> str:
    base = os.path.basename(name or "")
    stem, ext = os.path.splitext(base)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or "document"
    return stem[:80] + ext.lower()


def validate_upload(filename: str, data: bytes) -> None:
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise StorageError(f"Unsupported file type '{ext or 'none'}'. Allowed: PDF, PNG, JPG.")
    if not data:
        raise StorageError("The file is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise StorageError("The file is larger than the 10 MB limit.")


def folder_for(doc_type: str) -> str:
    return TYPE_FOLDERS.get(doc_type, "other")


def save_file(filename: str, data: bytes, doc_type: str = "unsorted", root: str = None) -> str:
    """Save bytes to storage/<type>/<unique safe name>; return the path."""
    root = root or STORAGE_ROOT
    folder = os.path.join(root, folder_for(doc_type) if doc_type != "unsorted" else "unsorted")
    try:
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{uuid.uuid4().hex[:8]}_{safe_filename(filename)}")
        with open(path, "wb") as fh:
            fh.write(data)
    except OSError as exc:
        raise StorageError("The file could not be saved to storage.") from exc
    return path


def move_to_type_folder(path: str, doc_type: str, root: str = None) -> str:
    """After classification, move the file into its document-type folder."""
    root = root or STORAGE_ROOT
    target_dir = os.path.join(root, folder_for(doc_type))
    try:
        os.makedirs(target_dir, exist_ok=True)
        target = os.path.join(target_dir, os.path.basename(path))
        if os.path.abspath(target) != os.path.abspath(path):
            os.replace(path, target)
        return target
    except OSError:
        return path  # keep the original location; not fatal


def read_file(path: str) -> bytes:
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError as exc:
        raise StorageError("The stored file could not be read.") from exc
