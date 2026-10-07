"""SQLite connection and database operations.

Tables
------
documents  : one row per stored document (metadata, extracted fields,
             validation results, workflow state).
audit_log  : append-only history of every workflow event (see audit.py).
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = "documents.db"


class DatabaseError(Exception):
    """Raised for any database failure so the UI never shows raw SQLite errors."""


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


@contextmanager
def get_conn(db_path: str = None):
    path = db_path or DB_PATH
    try:
        conn = sqlite3.connect(path, timeout=10)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        raise DatabaseError(f"Cannot open database: {exc}") from exc
    try:
        yield conn
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        raise DatabaseError(f"Database operation failed: {exc}") from exc
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    filename         TEXT NOT NULL,
    stored_path      TEXT NOT NULL,
    file_hash        TEXT NOT NULL UNIQUE,
    file_size        INTEGER,
    doc_type         TEXT DEFAULT 'Other',
    confidence       REAL,              -- NULL when the classifier gives none
    classifier       TEXT,              -- which classifier produced the type
    extracted_text   TEXT,
    fields_json      TEXT DEFAULT '{}',
    validation_json  TEXT DEFAULT '{}',
    status           TEXT NOT NULL DEFAULT 'New',
    review_reason    TEXT,
    uploaded_at      TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    processing_ms    INTEGER             -- NULL unless measured
);
CREATE INDEX IF NOT EXISTS idx_docs_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_docs_type   ON documents(doc_type);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    action      TEXT NOT NULL,
    old_status  TEXT,
    new_status  TEXT,
    timestamp   TEXT NOT NULL,
    note        TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_doc ON audit_log(document_id);
"""


def init_db(db_path: str = None) -> None:
    with get_conn(db_path) as conn:
        conn.executescript(SCHEMA)


def _row_to_dict(row) -> dict:
    d = dict(row)
    d["fields"] = json.loads(d.pop("fields_json") or "{}")
    d["validation"] = json.loads(d.pop("validation_json") or "{}")
    return d


def insert_document(filename, stored_path, file_hash, file_size, db_path=None) -> int:
    ts = now_iso()
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO documents
               (filename, stored_path, file_hash, file_size, status, uploaded_at, updated_at)
               VALUES (?,?,?,?,?,?,?)""",
            (filename, stored_path, file_hash, file_size, "New", ts, ts),
        )
        return cur.lastrowid


def find_by_hash(file_hash, db_path=None):
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM documents WHERE file_hash=?", (file_hash,)).fetchone()
    return _row_to_dict(row) if row else None


def get_document(doc_id, db_path=None):
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    return _row_to_dict(row) if row else None


def update_document(doc_id, db_path=None, **changes) -> None:
    """Update whitelisted columns. 'fields' and 'validation' are stored as JSON."""
    allowed = {"doc_type", "confidence", "classifier", "extracted_text", "status",
               "review_reason", "processing_ms", "fields", "validation"}
    cols, vals = [], []
    for key, value in changes.items():
        if key not in allowed:
            raise DatabaseError(f"Column not allowed: {key}")
        if key in ("fields", "validation"):
            key, value = key + "_json", json.dumps(value)
        cols.append(f"{key}=?")
        vals.append(value)
    cols.append("updated_at=?")
    vals.extend([now_iso(), doc_id])
    with get_conn(db_path) as conn:
        conn.execute(f"UPDATE documents SET {', '.join(cols)} WHERE id=?", vals)


def delete_document(doc_id, db_path=None) -> None:
    with get_conn(db_path) as conn:
        conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))


def list_documents(status=None, search=None, doc_type=None, db_path=None):
    """Return documents (newest first) with their latest audit action/timestamp.

    search matches filename, document type, company and invoice number.
    """
    sql = """
    SELECT d.*,
      (SELECT action    FROM audit_log a WHERE a.document_id=d.id ORDER BY a.id DESC LIMIT 1) AS last_action,
      (SELECT timestamp FROM audit_log a WHERE a.document_id=d.id ORDER BY a.id DESC LIMIT 1) AS last_action_at
    FROM documents d WHERE 1=1"""
    params = []
    if status and status != "All":
        sql += " AND d.status=?"
        params.append(status)
    if doc_type and doc_type != "All":
        sql += " AND d.doc_type=?"
        params.append(doc_type)
    if search:
        like = f"%{search.strip()}%"
        sql += """ AND (d.filename LIKE ? OR d.doc_type LIKE ?
                   OR json_extract(d.fields_json,'$.company_name') LIKE ?
                   OR json_extract(d.fields_json,'$.invoice_number') LIKE ?)"""
        params.extend([like] * 4)
    sql += " ORDER BY d.id DESC"
    with get_conn(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def metrics(db_path=None) -> dict:
    """Aggregate numbers for the dashboard (all computed from stored data)."""
    with get_conn(db_path) as conn:
        by_status = {r["status"]: r["n"] for r in conn.execute(
            "SELECT status, COUNT(*) n FROM documents GROUP BY status")}
        by_type = {r["doc_type"]: r["n"] for r in conn.execute(
            "SELECT doc_type, COUNT(*) n FROM documents GROUP BY doc_type")}
        avg = conn.execute(
            "SELECT AVG(processing_ms) a, COUNT(processing_ms) c FROM documents").fetchone()
        # failed = documents whose most recent audit action is a processing failure
        failed = conn.execute(
            """SELECT COUNT(*) n FROM documents d WHERE
               (SELECT action FROM audit_log a WHERE a.document_id=d.id
                ORDER BY a.id DESC LIMIT 1) = 'Processing failed'"""
        ).fetchone()["n"]
    total = sum(by_status.values())
    return {
        "total": total,
        "by_status": by_status,
        "by_type": by_type,
        "processed": total - by_status.get("New", 0) - by_status.get("Processing", 0),
        "needs_review": by_status.get("Needs Review", 0),
        "approved": by_status.get("Approved", 0),
        "rejected": by_status.get("Rejected", 0),
        "completed": by_status.get("Completed", 0),
        "failed": failed,
        "avg_processing_ms": round(avg["a"]) if avg["c"] else None,
        "timed_documents": avg["c"],
    }
