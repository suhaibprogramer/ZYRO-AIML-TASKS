"""SQLite storage: documents, audit log, text chunks (for the AI assistant),
assistant question log and rejected-upload log.

All paths come from config.DB_PATH at call time. WAL mode lets the Streamlit UI
and the API share one database safely.
"""
import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

import config

log = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Raised for any database failure. The message is safe to show to users."""


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


@contextmanager
def get_conn():
    try:
        conn = sqlite3.connect(config.DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
    except sqlite3.Error as exc:
        log.error("Cannot open database %s: %s", config.DB_PATH, exc)
        raise DatabaseError("The database is unavailable right now. Please try again.") from exc
    try:
        yield conn
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        log.error("Database operation failed: %s", exc)
        raise DatabaseError("A database operation failed. Please try again.") from exc
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
    confidence       REAL,               -- NULL when the classifier gives no probability
    classifier       TEXT,
    text_method      TEXT,               -- pdf-text or ocr
    extracted_text   TEXT,
    fields_json      TEXT DEFAULT '{}',
    validation_json  TEXT DEFAULT '{}',
    anomalies_json   TEXT DEFAULT '[]',
    timings_json     TEXT DEFAULT '{}',  -- milliseconds per pipeline stage
    status           TEXT NOT NULL DEFAULT 'New',
    review_reason    TEXT,
    uploaded_at      TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    processing_ms    INTEGER
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

CREATE TABLE IF NOT EXISTS chunks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    text        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(document_id);

CREATE TABLE IF NOT EXISTS qa_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    question     TEXT NOT NULL,
    grounded     INTEGER NOT NULL,       -- 1 = answered from documents, 0 = not enough information
    top_score    REAL,
    coverage     REAL,
    sources_json TEXT DEFAULT '[]',
    asked_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS upload_rejections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    filename    TEXT,
    code        TEXT,
    reason      TEXT,
    rejected_at TEXT NOT NULL
);
"""

# Columns added after the Week 5 schema; added automatically to older databases.
_MIGRATIONS = {
    "anomalies_json": "TEXT DEFAULT '[]'",
    "timings_json": "TEXT DEFAULT '{}'",
    "text_method": "TEXT",
}


def init_db() -> None:
    import os
    parent = os.path.dirname(config.DB_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        existing = {r["name"] for r in conn.execute("PRAGMA table_info(documents)")}
        for col, ddl in _MIGRATIONS.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE documents ADD COLUMN {col} {ddl}")


def _row_to_dict(row) -> dict:
    d = dict(row)
    d["fields"] = json.loads(d.pop("fields_json", None) or "{}")
    d["validation"] = json.loads(d.pop("validation_json", None) or "{}")
    d["anomalies"] = json.loads(d.pop("anomalies_json", None) or "[]")
    d["timings"] = json.loads(d.pop("timings_json", None) or "{}")
    return d


# ------------------------------------------------------------------ documents
def insert_document(filename, stored_path, file_hash, file_size) -> int:
    ts = now_iso()
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO documents (filename, stored_path, file_hash, file_size, status, uploaded_at, updated_at)
               VALUES (?,?,?,?,?,?,?)""",
            (filename, stored_path, file_hash, file_size, "New", ts, ts))
        return cur.lastrowid


def find_by_hash(file_hash) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM documents WHERE file_hash=?", (file_hash,)).fetchone()
    return _row_to_dict(row) if row else None


def get_document(doc_id) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    return _row_to_dict(row) if row else None


_JSON_COLUMNS = {"fields": "fields_json", "validation": "validation_json",
                 "anomalies": "anomalies_json", "timings": "timings_json"}
_PLAIN_COLUMNS = {"doc_type", "confidence", "classifier", "extracted_text", "status", "review_reason",
                  "processing_ms", "text_method", "stored_path"}


def update_document(doc_id, **changes) -> None:
    """Update whitelisted columns. fields/validation/anomalies/timings are stored as JSON."""
    cols, vals = [], []
    for key, value in changes.items():
        if key in _JSON_COLUMNS:
            cols.append(f"{_JSON_COLUMNS[key]}=?")
            vals.append(json.dumps(value))
        elif key in _PLAIN_COLUMNS:
            cols.append(f"{key}=?")
            vals.append(value)
        else:
            raise DatabaseError(f"Column not allowed: {key}")
    cols.append("updated_at=?")
    vals.extend([now_iso(), doc_id])
    with get_conn() as conn:
        conn.execute(f"UPDATE documents SET {', '.join(cols)} WHERE id=?", vals)


def delete_document(doc_id) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))  # chunks cascade


def list_documents(status=None, search=None, doc_type=None) -> list:
    """Newest first, each with its latest audit action and time.

    `search` matches filename, type, company, invoice number, person name and email.
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
    if search and search.strip():
        like = f"%{search.strip()}%"
        sql += """ AND (d.filename LIKE ? OR d.doc_type LIKE ?
                   OR json_extract(d.fields_json,'$.company_name') LIKE ?
                   OR json_extract(d.fields_json,'$.invoice_number') LIKE ?
                   OR json_extract(d.fields_json,'$.name') LIKE ?
                   OR json_extract(d.fields_json,'$.email') LIKE ?)"""
        params.extend([like] * 6)
    sql += " ORDER BY d.id DESC"
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


_FIELD_WHITELIST = {"invoice_number", "email", "total_amount"}


def find_by_field(doc_type: str, field: str, value: str, exclude_id: int) -> list:
    """Other documents of this type whose extracted field equals `value` (case-insensitive)."""
    if field not in _FIELD_WHITELIST:
        raise DatabaseError("Field not allowed.")
    with get_conn() as conn:
        rows = conn.execute(
            f"""SELECT id, filename, status FROM documents
                WHERE doc_type=? AND id!=? AND lower(json_extract(fields_json,'$.{field}'))=lower(?)""",
            (doc_type, exclude_id, value)).fetchall()
    return [dict(r) for r in rows]


def field_values(doc_type: str, field: str, exclude_id: int) -> list:
    """Extracted values of a field from other processed (non-rejected) documents of a type."""
    if field not in _FIELD_WHITELIST:
        raise DatabaseError("Field not allowed.")
    with get_conn() as conn:
        rows = conn.execute(
            f"""SELECT json_extract(fields_json,'$.{field}') AS v FROM documents
                WHERE doc_type=? AND id!=? AND status NOT IN ('New','Processing','Rejected')""",
            (doc_type, exclude_id)).fetchall()
    return [r["v"] for r in rows if r["v"] is not None]


def stuck_processing_ids() -> list:
    with get_conn() as conn:
        return [r["id"] for r in conn.execute("SELECT id FROM documents WHERE status='Processing'")]


# --------------------------------------------------------------------- chunks
def replace_chunks(doc_id: int, chunks: list) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM chunks WHERE document_id=?", (doc_id,))
        conn.executemany("INSERT INTO chunks (document_id, chunk_index, text) VALUES (?,?,?)",
                         [(doc_id, i, c) for i, c in enumerate(chunks)])


def get_chunks(doc_id: int) -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM chunks WHERE document_id=? ORDER BY chunk_index", (doc_id,))
        return [dict(r) for r in rows]


def eligible_chunks() -> list:
    """Chunks the assistant may use: every processed document except rejected ones."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT c.id, c.document_id, c.chunk_index, c.text, d.filename, d.status, d.doc_type
               FROM chunks c JOIN documents d ON d.id=c.document_id
               WHERE d.status NOT IN ('Rejected','New','Processing')
               ORDER BY c.id""").fetchall()
    return [dict(r) for r in rows]


def chunk_stamp() -> tuple:
    """A cheap fingerprint of the eligible chunks; the search index is rebuilt only when it changes."""
    with get_conn() as conn:
        r = conn.execute(
            """SELECT COUNT(*) n, COALESCE(MAX(c.id),0) m, COALESCE(SUM(c.id),0) s
               FROM chunks c JOIN documents d ON d.id=c.document_id
               WHERE d.status NOT IN ('Rejected','New','Processing')""").fetchone()
    return (r["n"], r["m"], r["s"])


# ------------------------------------------------------------- assistant log
def log_question(question, grounded, top_score, coverage, sources) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO qa_log (question, grounded, top_score, coverage, sources_json, asked_at)
               VALUES (?,?,?,?,?,?)""",
            (question, 1 if grounded else 0, top_score, coverage, json.dumps(sources), now_iso()))


def recent_questions(limit=20, only_unanswered=False) -> list:
    sql = "SELECT * FROM qa_log"
    if only_unanswered:
        sql += " WHERE grounded=0"
    sql += " ORDER BY id DESC LIMIT ?"
    with get_conn() as conn:
        rows = conn.execute(sql, (limit,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["sources"] = json.loads(d.pop("sources_json") or "[]")
        out.append(d)
    return out


# ---------------------------------------------------------- upload rejections
def log_rejection(filename, code, reason) -> None:
    with get_conn() as conn:
        conn.execute("INSERT INTO upload_rejections (filename, code, reason, rejected_at) VALUES (?,?,?,?)",
                     (filename, code, reason, now_iso()))


def recent_rejections(limit=20) -> list:
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM upload_rejections ORDER BY id DESC LIMIT ?", (limit,))]


# -------------------------------------------------------------------- metrics
def metrics() -> dict:
    """Every dashboard number, computed from stored data."""
    with get_conn() as conn:
        by_status = {r["status"]: r["n"] for r in conn.execute(
            "SELECT status, COUNT(*) n FROM documents GROUP BY status")}
        by_type = {r["doc_type"]: r["n"] for r in conn.execute(
            "SELECT doc_type, COUNT(*) n FROM documents GROUP BY doc_type")}
        avg = conn.execute("SELECT AVG(processing_ms) a, COUNT(processing_ms) c FROM documents").fetchone()
        failed = conn.execute(
            """SELECT COUNT(*) n FROM documents d WHERE
               (SELECT action FROM audit_log a WHERE a.document_id=d.id ORDER BY a.id DESC LIMIT 1)
               = 'Processing failed'""").fetchone()["n"]
        duplicates = conn.execute(
            "SELECT COUNT(*) n FROM audit_log WHERE action='Duplicate upload blocked'").fetchone()["n"]
        rejected_uploads = conn.execute("SELECT COUNT(*) n FROM upload_rejections").fetchone()["n"]
        validation_failed = conn.execute(
            """SELECT COUNT(*) n FROM documents WHERE doc_type IN ('Invoice','Resume')
               AND json_extract(validation_json,'$.valid')=0""").fetchone()["n"]
        validation_passed = conn.execute(
            """SELECT COUNT(*) n FROM documents WHERE doc_type IN ('Invoice','Resume')
               AND json_extract(validation_json,'$.valid')=1""").fetchone()["n"]
        anomaly_rows = [json.loads(r["a"]) for r in conn.execute(
            "SELECT anomalies_json a FROM documents WHERE anomalies_json!='[]'")]
        timing_rows = [json.loads(r["t"]) for r in conn.execute(
            "SELECT timings_json t FROM documents WHERE timings_json!='{}'")]
        qa_total = conn.execute("SELECT COUNT(*) n FROM qa_log").fetchone()["n"]
        qa_unanswered = conn.execute("SELECT COUNT(*) n FROM qa_log WHERE grounded=0").fetchone()["n"]

    anomaly_by_code = {}
    for items in anomaly_rows:
        for a in items:
            anomaly_by_code[a["code"]] = anomaly_by_code.get(a["code"], 0) + 1

    sums, counts = {}, {}
    for t in timing_rows:
        for stage, ms in t.items():
            if stage == "total":
                continue
            sums[stage] = sums.get(stage, 0) + ms
            counts[stage] = counts.get(stage, 0) + 1
    stage_avg = {s: round(sums[s] / counts[s], 1) for s in sums}

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
        "duplicates_blocked": duplicates,
        "rejected_uploads": rejected_uploads,
        "validation_passed": validation_passed,
        "validation_failed": validation_failed,
        "documents_with_anomalies": len(anomaly_rows),
        "anomalies_by_code": anomaly_by_code,
        "avg_processing_ms": round(avg["a"]) if avg["c"] else None,
        "timed_documents": avg["c"],
        "stage_avg_ms": stage_avg,
        "slowest_stage": max(stage_avg, key=stage_avg.get) if stage_avg else None,
        "questions_asked": qa_total,
        "questions_unanswered": qa_unanswered,
    }
