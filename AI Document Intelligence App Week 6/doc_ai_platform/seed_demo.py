"""Load the sample corpus into the configured database for a live demo or screenshots.

Run:  python make_samples.py && python seed_demo.py
Uses DB_PATH / STORAGE_ROOT from the environment (see .env.example), so point APP_DATA_DIR at a scratch folder
if you do not want to touch your real data.
"""
import io
import json
import os

import database as db
import rag
import service


def invoice_pdf(number, company, total):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for line in [company, "INVOICE", f"Invoice No: {number}", "Date: 2025-10-01", "Bill To: Demo Customer Co",
                 f"Total Amount: {total}", "Payment terms: net 30"]:
        c.drawString(60, y, line)
        y -= 24
    c.save()
    return buf.getvalue()


def main():
    db.init_db()
    manifest = json.load(open("sample_docs/manifest.json"))
    for e in manifest["documents"]:
        service.upload_and_process(e["file"], open(os.path.join("sample_docs", e["file"]), "rb").read())
    for r in manifest["rejected_uploads"]:                      # shows up under "rejected uploads"
        service.ingest(r["file"], open(os.path.join("sample_docs", r["file"]), "rb").read())
    service.ingest("again_acme.pdf", open("sample_docs/invoice_acme.pdf", "rb").read())  # duplicate
    for n, (num, co, tot) in enumerate([("DEMO-1", "Maple Foods Ltd", "$120.00"), ("DEMO-2", "River Tools Inc", "$75.50"),
                                        ("DEMO-3", "Summit Books LLC", "$310.00")]):
        service.ingest(f"waiting_{n + 1}.pdf", invoice_pdf(num, co, tot))   # left in state New for Batch page
    for q in ["What is the total amount on invoice HL-310?", "What skills does Sara Khan have?",
              "What is the refund policy?"]:
        rag.ask(q)
    print("Demo data loaded:", db.metrics()["total"], "documents")


if __name__ == "__main__":
    main()
