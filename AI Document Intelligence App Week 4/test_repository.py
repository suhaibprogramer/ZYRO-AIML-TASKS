"""
Week 4, Task 9 - test the complete repository.

Uses a temporary database and temporary storage folder, so your real data
is never touched. Writes the evidence to reports/week4_test_results.md.

Run:  python test_repository.py
"""

import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import database as db
import document_processor as dp
import service
import storage

ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "samples" / "week4"
BAD = SAMPLES / "bad_files"

checks: list[tuple[str, str, str, bool]] = []   # (what, expected, actual, passed)


def check(what, expected, actual):
    checks.append((what, str(expected), str(actual), expected == actual))


# ---- Use a temporary database + storage folder ----
tmp = Path(tempfile.mkdtemp(prefix="week4_test_"))
db.DB_PATH = tmp / "data" / "documents.db"
storage.STORAGE_ROOT = tmp / "storage"
db.init_db()


def upload(path: Path) -> dict:
    return service.ingest_document(path.name, path.read_bytes())


# ------------------------------------------------------------------ #
# 1. Upload valid documents
# ------------------------------------------------------------------ #
expected_docs = [
    # filename,                     type,      status
    ("invoice_001.pdf",             "Invoice", "Processed"),
    ("invoice_002.pdf",             "Invoice", "Processed"),
    ("invoice_003.pdf",             "Invoice", "Processed"),
    ("invoice_004.pdf",             "Invoice", "Processed"),
    ("invoice_missing_fields.pdf",  "Invoice", "Needs Review"),
    ("resume_001.pdf",              "Resume",  "Processed"),
    ("resume_002.pdf",              "Resume",  "Processed"),
    ("resume_missing_email.pdf",    "Resume",  "Needs Review"),
    ("other_meeting_minutes.pdf",   "Other",   "Processed"),
    ("other_recipe.pdf",            "Other",   "Processed"),
    ("scanned_invoice.png",         "Invoice", "Processed"),
    ("scanned_resume.png",          "Resume",  "Processed"),
]

saved_rows = []
ids = {}
for filename, exp_type, exp_status in expected_docs:
    out = upload(SAMPLES / filename)
    check(f"Upload {filename}: outcome", "saved", out["outcome"])
    if out["outcome"] == "saved":
        d = out["document"]
        ids[filename] = d["id"]
        saved_rows.append(d)
        check(f"Upload {filename}: document type", exp_type, d["document_type"])
        check(f"Upload {filename}: status", exp_status, d["status"])

# ------------------------------------------------------------------ #
# 2. Duplicate detection
# ------------------------------------------------------------------ #
out = upload(SAMPLES / "invoice_001_duplicate.pdf")
check("Duplicate (same content, new name): outcome", "duplicate", out["outcome"])
check("Duplicate points to the ORIGINAL record", ids["invoice_001.pdf"],
      out.get("document", {}).get("id"))
check("Duplicate did not create a new record", len(expected_docs), db.count_documents())

# ------------------------------------------------------------------ #
# 3. Error handling
# ------------------------------------------------------------------ #
out = upload(BAD / "notes.txt")
check("Unsupported type (.txt) is rejected", "rejected", out["outcome"])

out = upload(BAD / "fake_image.png")
check("Fake image (text renamed .png) is rejected", "rejected", out["outcome"])

out = service.ingest_document("empty.pdf", b"")
check("Empty file is rejected", "rejected", out["outcome"])

out = service.ingest_document("huge.pdf", b"%PDF" + b"0" * (storage.MAX_UPLOAD_BYTES + 1))
check("Oversized file (>10 MB) is rejected", "rejected", out["outcome"])

before = db.count_documents()
out = upload(BAD / "corrupt.pdf")
check("Corrupt PDF does not crash (saved as Failed)", "saved", out["outcome"])
if out["outcome"] == "saved":
    check("Corrupt PDF status", "Failed", out["document"]["status"])
    msg = out["document"]["status_note"] or ""
    check("Corrupt PDF message is friendly (no raw exception)",
          True, bool(msg) and "Traceback" not in msg and "Error(" not in msg)
check("Corrupt PDF was tracked as a record", before + 1, db.count_documents())

# OCR failure must not crash: pretend OCR is not installed
original_flag = dp.OCR_AVAILABLE
dp.OCR_AVAILABLE = False
res = dp.process_document((SAMPLES / "scanned_invoice.png").read_bytes(), "png")
dp.OCR_AVAILABLE = original_flag
check("OCR unavailable: no crash, status Failed", "Failed", res["status"])
check("OCR unavailable: friendly message", True, bool(res["error"]))

# ------------------------------------------------------------------ #
# 4. Storage structure
# ------------------------------------------------------------------ #
all_docs = db.search_documents()
folders_ok = all(
    storage.absolute_path(d["file_path"]).exists()
    and f"/{storage.FOLDER_FOR_TYPE[d['document_type']]}/" in "/" + d["file_path"]
    for d in all_docs
)
check("Every file exists in the correct folder for its type", True, folders_ok)
check("Stored filenames are generated (not the original names)", True,
      all(d["stored_filename"] != d["original_filename"] for d in all_docs))
check("Original filenames are kept in the database", True,
      {"invoice_001.pdf", "resume_002.pdf"} <= {d["original_filename"] for d in all_docs})
check("invoices/ folder holds only Invoice files", True,
      all(any(d["stored_filename"] == p.name for d in all_docs if d["document_type"] == "Invoice")
          for p in (storage.STORAGE_ROOT / "invoices").iterdir()))

# ------------------------------------------------------------------ #
# 5. Search (different fields)
# ------------------------------------------------------------------ #
def search_names(**kw):
    return sorted(d["original_filename"] for d in db.search_documents(**kw))

check("Search by company 'Delta'", ["invoice_missing_fields.pdf"], search_names(query="Delta"))
check("Search by invoice number 'INV-3310'", ["invoice_003.pdf"], search_names(query="INV-3310"))
check("Search by file name 'scanned'", ["scanned_invoice.png", "scanned_resume.png"],
      search_names(query="scanned"))
check("Search by text preview 'vegetable'", ["other_recipe.pdf"], search_names(query="vegetable"))
check("Search by document type word 'Resume' finds all resumes", True,
      {"resume_001.pdf", "resume_002.pdf", "resume_missing_email.pdf"}
      <= set(search_names(query="Resume")))
check("Search with no match returns nothing", [], search_names(query="zzzznotfound"))
check("Search '%' is treated as text, not a wildcard", [], search_names(query="%"))

# ------------------------------------------------------------------ #
# 6. Filters and sorting
# ------------------------------------------------------------------ #
check("Filter type=Invoice count", 6, len(db.search_documents(document_type="Invoice")))
check("Filter type=Resume count", 4, len(db.search_documents(document_type="Resume")))
check("Filter status='Needs Review' count", 2, len(db.search_documents(status="Needs Review")))
check("Filter status=Failed count", 1, len(db.search_documents(status="Failed")))
check("Combined filter: Invoice + Needs Review", ["invoice_missing_fields.pdf"],
      search_names(document_type="Invoice", status="Needs Review"))

today = date.today()
check("Date filter (today) includes all", db.count_documents(),
      len(db.search_documents(date_from=today.isoformat(), date_to=today.isoformat())))
yesterday = (today - timedelta(days=1)).isoformat()
check("Date filter (yesterday only) includes none", 0,
      len(db.search_documents(date_from=yesterday, date_to=yesterday)))

newest = [d["id"] for d in db.search_documents(newest_first=True)]
oldest = [d["id"] for d in db.search_documents(newest_first=False)]
check("Sort oldest-first is the reverse of newest-first", newest[::-1], oldest)
check("Newest first puts the last upload on top", max(newest), newest[0])

# ------------------------------------------------------------------ #
# 7. Update and delete
# ------------------------------------------------------------------ #
rid = ids["resume_missing_email.pdf"]
check("Update status to Processed", True, db.update_document(rid, {"status": "Processed"}))
check("Status change was saved", "Processed", db.get_document(rid)["status"])
check("Unknown columns cannot be updated", False, db.update_document(rid, {"file_hash": "x"}))

victim = db.get_document(ids["other_recipe.pdf"])
path_before = storage.absolute_path(victim["file_path"])
db.delete_document(victim["id"])
storage.delete_file(victim["file_path"])
check("Delete removes the record", None, db.get_document(victim["id"]))
check("Delete removes the file", False, path_before.exists())

# ------------------------------------------------------------------ #
# 8. Restart: a brand-new Python process must still see the records
# ------------------------------------------------------------------ #
expected_count = db.count_documents()
code = (
    "import sys; from pathlib import Path; import database as db; "
    f"db.DB_PATH = Path(r'{db.DB_PATH}'); print(db.count_documents())"
)
proc = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
check("After restart (new process) saved records remain", str(expected_count),
      proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else proc.stderr[-200:])

# ------------------------------------------------------------------ #
# 9. Database error handling (a broken database file)
# ------------------------------------------------------------------ #
good_db = db.DB_PATH
bad_db = tmp / "broken.db"
bad_db.write_text("this is not a sqlite database")
db.DB_PATH = bad_db
files_before = sum(1 for _ in storage.STORAGE_ROOT.rglob("*") if _.is_file())
out = service.ingest_document("late_invoice.pdf", (SAMPLES / "invoice_003.pdf").read_bytes())
db.DB_PATH = good_db
files_after = sum(1 for _ in storage.STORAGE_ROOT.rglob("*") if _.is_file())
check("Broken database: clear error outcome (no crash)", "error", out["outcome"])
check("Broken database: message hides technical details", True,
      "sqlite" not in out.get("message", "").lower() and "file is not a database" not in out.get("message", "").lower())
check("Broken database: no orphan file left behind", files_before, files_after)

# ------------------------------------------------------------------ #
# Report
# ------------------------------------------------------------------ #
passed = sum(1 for c in checks if c[3])
lines = [
    "# Week 4 - Test Results\n",
    f"Run date: {date.today().isoformat()}  \n",
    f"Documents tested: {len(expected_docs)} valid + duplicate + 5 bad/edge-case files\n",
    f"\n**Result: {passed} / {len(checks)} checks passed**\n",
    "\n## Documents processed\n",
    "| # | File | Type | Confidence | Status | Note |\n|---|---|---|---|---|---|\n",
]
for d in saved_rows:
    conf = f"{d['confidence'] * 100:.0f}%" if d["confidence"] is not None else "-"
    lines.append(f"| {d['id']} | {d['original_filename']} | {d['document_type']} | {conf} | "
                 f"{d['status']} | {d['status_note'] or ''} |\n")

lines += ["\n## All checks\n", "| Result | Check | Expected | Actual |\n|---|---|---|---|\n"]
for what, exp, act, ok in checks:
    esc = lambda s: s.replace("|", "\\|").replace("\n", " ")[:90]
    lines.append(f"| {'PASS' if ok else '**FAIL**'} | {what} | {esc(exp)} | {esc(act)} |\n")

(ROOT / "reports").mkdir(exist_ok=True)
(ROOT / "reports" / "week4_test_results.md").write_text("".join(lines), encoding="utf-8")

print(f"{passed} / {len(checks)} checks passed")
for what, exp, act, ok in checks:
    if not ok:
        print(f"  FAIL: {what}\n        expected: {exp}\n        actual:   {act}")
