"""
SQLite document repository (Week 4, Task 2/4/5).

All database code lives here. The Streamlit app never writes SQL.
Every function raises DatabaseError (with a friendly message) if SQLite fails.
"""

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "documents.db"   # tests may change this


class DatabaseError(Exception):
    """A database problem, with a message that is safe to show to users."""


class DuplicateHashError(Exception):
    """A document with the same file hash is already saved."""


SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    original_filename TEXT NOT NULL,
    stored_filename   TEXT NOT NULL,
    document_type     TEXT NOT NULL,
    confidence        REAL,
    upload_date       TEXT NOT NULL,
    company           TEXT,
    invoice_number    TEXT,
    invoice_date      TEXT,
    total_amount      TEXT,
    person_name       TEXT,
    email             TEXT,
    phone             TEXT,
    skills            TEXT,
    file_path         TEXT NOT NULL,
    file_size         INTEGER,
    extraction_method TEXT,
    text_preview      TEXT,
    file_hash         TEXT NOT NULL UNIQUE,
    status            TEXT NOT NULL,
    status_note       TEXT
);
CREATE INDEX IF NOT EXISTS idx_documents_type   ON documents(document_type);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_date   ON documents(upload_date);
"""

COLUMNS = [
    "original_filename", "stored_filename", "document_type", "confidence",
    "upload_date", "company", "invoice_number", "invoice_date", "total_amount",
    "person_name", "email", "phone", "skills", "file_path", "file_size",
    "extraction_method", "text_preview", "file_hash", "status", "status_note",
]

# Only these columns may be changed by update_document()
UPDATABLE = {
    "document_type", "status", "status_note", "company", "invoice_number",
    "invoice_date", "total_amount", "person_name", "email", "phone", "skills",
}

# Columns that the search box looks in
SEARCH_COLUMNS = [
    "original_filename", "company", "invoice_number", "document_type",
    "text_preview", "person_name", "email", "skills",
]

FRIENDLY_ERROR = "The document database could not be used right now. Please try again."


@contextmanager
def _connect():
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
    except (sqlite3.Error, OSError):
        logger.exception("Could not open database")
        raise DatabaseError(FRIENDLY_ERROR)
    try:
        yield conn
        conn.commit()
    except DuplicateHashError:
        conn.rollback()
        raise
    except sqlite3.Error:
        conn.rollback()
        logger.exception("Database error")
        raise DatabaseError(FRIENDLY_ERROR)
    finally:
        conn.close()


def init_db() -> None:
    """Create the documents table if it does not exist yet."""
    with _connect() as conn:
        conn.executescript(SCHEMA)


# ----------------------------- Create ----------------------------- #

def insert_document(record: dict) -> int:
    """Save one document. Returns its new id. Raises DuplicateHashError if hash exists."""
    values = [record.get(c) for c in COLUMNS]
    sql = f"INSERT INTO documents ({', '.join(COLUMNS)}) VALUES ({', '.join('?' * len(COLUMNS))})"
    with _connect() as conn:
        try:
            cur = conn.execute(sql, values)
        except sqlite3.IntegrityError:
            raise DuplicateHashError()
        return cur.lastrowid


# ----------------------------- Read ----------------------------- #

def get_document(doc_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        return dict(row) if row else None


def get_document_by_hash(file_hash: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM documents WHERE file_hash = ?", (file_hash,)).fetchone()
        return dict(row) if row else None


def count_documents() -> int:
    with _connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_documents(query: str = "", document_type: str | None = None,
                     status: str | None = None, date_from: str | None = None,
                     date_to: str | None = None, newest_first: bool = True) -> list[dict]:
    """
    Search + filter + sort, all done inside SQLite.
    date_from / date_to are 'YYYY-MM-DD' strings (inclusive).
    """
    where, params = [], []

    query = (query or "").strip()
    if query:
        like = f"%{_escape_like(query)}%"
        where.append("(" + " OR ".join(f"{c} LIKE ? ESCAPE '\\'" for c in SEARCH_COLUMNS) + ")")
        params.extend([like] * len(SEARCH_COLUMNS))
    if document_type:
        where.append("document_type = ?")
        params.append(document_type)
    if status:
        where.append("status = ?")
        params.append(status)
    if date_from:
        where.append("date(upload_date) >= date(?)")
        params.append(date_from)
    if date_to:
        where.append("date(upload_date) <= date(?)")
        params.append(date_to)

    sql = "SELECT * FROM documents"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY upload_date {0}, id {0}".format("DESC" if newest_first else "ASC")

    with _connect() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


# ----------------------------- Update ----------------------------- #

def update_document(doc_id: int, updates: dict) -> bool:
    """Change allowed columns of one document. Returns True if a row changed."""
    clean = {k: v for k, v in updates.items() if k in UPDATABLE}
    if not clean:
        return False
    assignments = ", ".join(f"{k} = ?" for k in clean)
    with _connect() as conn:
        cur = conn.execute(f"UPDATE documents SET {assignments} WHERE id = ?",
                           [*clean.values(), doc_id])
        return cur.rowcount > 0


# ----------------------------- Delete ----------------------------- #

def delete_document(doc_id: int) -> str | None:
    """Delete one record. Returns its file_path (so the caller can delete the file) or None."""
    with _connect() as conn:
        row = conn.execute("SELECT file_path FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not row:
            return None
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        return row["file_path"]
