"""Workflow history and audit logging.

Every important event is written to the audit_log table, so a document's full
history can be traced: document ID, action, previous status, new status,
timestamp (UTC) and a reason / reviewer note. Audit rows are never deleted.
"""
from database import get_conn, now_iso


def log_event(document_id, action, old_status=None, new_status=None, note=None):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO audit_log (document_id, action, old_status, new_status, timestamp, note)
               VALUES (?,?,?,?,?,?)""",
            (document_id, action, old_status, new_status, now_iso(), note))


def get_history(document_id):
    """Full history of one document, oldest first."""
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM audit_log WHERE document_id=? ORDER BY id ASC",
                            (document_id,)).fetchall()
    return [dict(r) for r in rows]


def get_recent(limit=25):
    """Most recent workflow events across all documents, newest first."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT a.id, a.document_id, d.filename, a.action, a.old_status, a.new_status,
                      a.timestamp, a.note
               FROM audit_log a LEFT JOIN documents d ON d.id=a.document_id
               ORDER BY a.id DESC LIMIT ?""", (limit,)).fetchall()
    return [dict(r) for r in rows]
