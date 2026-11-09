"""Reporting: a flat CSV export of every document and its workflow result."""
import csv
import io

import database as db

COLUMNS = ["id", "filename", "doc_type", "status", "company_or_name", "invoice_number", "total_amount",
           "confidence", "field_completeness", "anomalies", "review_reason", "uploaded_at", "updated_at",
           "processing_ms"]


def documents_csv() -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=COLUMNS)
    writer.writeheader()
    for d in db.list_documents():
        f = d["fields"]
        writer.writerow({
            "id": d["id"], "filename": d["filename"], "doc_type": d["doc_type"], "status": d["status"],
            "company_or_name": f.get("company_name") or f.get("name") or "",
            "invoice_number": f.get("invoice_number", ""), "total_amount": f.get("total_amount", ""),
            "confidence": "" if d["confidence"] is None else round(d["confidence"], 3),
            "field_completeness": d["validation"].get("completeness", ""),
            "anomalies": ";".join(a["code"] for a in d["anomalies"]),
            "review_reason": d["review_reason"] or "", "uploaded_at": d["uploaded_at"],
            "updated_at": d["updated_at"], "processing_ms": d["processing_ms"] or ""})
    return out.getvalue()
