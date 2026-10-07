"""Workflow history and audit logging.

Every important workflow event is written to the audit_log table so a
document's full history can be traced: Document ID, Action, Previous status,
New status, Timestamp, Reason / reviewer note.
"""
from database import get_conn, now_iso


def log_event(document_id, action, old_status=None, new_status=None, note=None, db_path=None):
    with get_conn(db_path) as conn:
        conn.execute(
            """INSERT INTO audit_log (document_id, action, old_status, new_status, timestamp, note)
               VALUES (?,?,?,?,?,?)""",
            (document_id, action, old_status, new_status, now_iso(), note),
        )


def get_history(document_id, db_path=None):
    """Full history of one document, oldest first."""
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE document_id=? ORDER BY id ASC", (document_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_recent(limit=50, db_path=None):
    with get_conn(db_path) as conn:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]
