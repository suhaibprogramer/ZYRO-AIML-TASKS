"""File storage, upload validation and safe paths."""
import hashlib
import os
import re
import uuid

import config

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
# The first bytes of a real file of each type. A renamed .exe or text file fails this.
MAGIC_BYTES = {
    ".pdf": (b"%PDF-",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
}
TYPE_FOLDERS = {"Invoice": "invoices", "Resume": "resumes"}


class StorageError(Exception):
    """A rejected file or a disk problem. The message is safe to show to users.

    `code` is a short machine-readable reason used by the API:
    unsupported_type, empty, too_large, invalid_content, path_denied, storage.
    """

    def __init__(self, message: str, code: str = "storage"):
        super().__init__(message)
        self.code = code


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_filename(name: str) -> str:
    """Strip any directory part and unsafe characters from a user-supplied name."""
    base = os.path.basename((name or "").replace("\\", "/"))
    stem, ext = os.path.splitext(base)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or "document"
    return stem[:80] + ext.lower()


def validate_upload(filename: str, data: bytes) -> None:
    """Check extension, size and that the content really is that file type."""
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise StorageError(f"Unsupported file type '{ext or 'none'}'. Allowed: PDF, PNG, JPG.",
                           "unsupported_type")
    if not data:
        raise StorageError("The file is empty.", "empty")
    if len(data) > config.MAX_FILE_BYTES:
        limit_mb = config.MAX_FILE_BYTES / (1024 * 1024)
        raise StorageError(f"The file is larger than the {limit_mb:g} MB limit.", "too_large")
    if not any(data.startswith(sig) for sig in MAGIC_BYTES[ext]):
        raise StorageError(f"The content of this file does not match a valid {ext[1:].upper()} file.",
                           "invalid_content")


def folder_for(doc_type: str) -> str:
    return TYPE_FOLDERS.get(doc_type, "other")


def _inside_root(path: str) -> bool:
    """True only if `path` really lives under the storage root (blocks ../ and symlink tricks)."""
    root = os.path.realpath(config.STORAGE_ROOT)
    target = os.path.realpath(path)
    try:
        return os.path.commonpath([root, target]) == root
    except ValueError:  # different drives on Windows
        return False


def save_file(filename: str, data: bytes, doc_type: str = "unsorted") -> str:
    """Save bytes to <storage root>/<type folder>/<random id>_<safe name>."""
    sub = "unsorted" if doc_type == "unsorted" else folder_for(doc_type)
    folder = os.path.join(config.STORAGE_ROOT, sub)
    path = os.path.join(folder, f"{uuid.uuid4().hex[:12]}_{safe_filename(filename)}")
    if not _inside_root(path):
        raise StorageError("That storage location is not allowed.", "path_denied")
    try:
        os.makedirs(folder, exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)
    except OSError as exc:
        raise StorageError("The file could not be saved to storage.", "storage") from exc
    return path


def move_to_type_folder(path: str, doc_type: str) -> str:
    """After classification, move the file into its document-type folder."""
    if not _inside_root(path):
        return path
    target_dir = os.path.join(config.STORAGE_ROOT, folder_for(doc_type))
    try:
        os.makedirs(target_dir, exist_ok=True)
        target = os.path.join(target_dir, os.path.basename(path))
        if os.path.abspath(target) != os.path.abspath(path):
            os.replace(path, target)
        return target
    except OSError:
        return path  # keep the original location; not fatal


def read_file(path: str) -> bytes:
    """Read a stored file. Refuses any path outside the storage root."""
    if not _inside_root(path):
        raise StorageError("Access to that file location is not allowed.", "path_denied")
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError as exc:
        raise StorageError("The stored file could not be read.", "storage") from exc


def remove_quietly(path: str) -> None:
    try:
        if _inside_root(path):
            os.remove(path)
    except OSError:
        pass
