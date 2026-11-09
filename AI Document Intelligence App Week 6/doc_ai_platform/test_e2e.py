"""End-to-end test suite for the whole platform.

Run:  python test_e2e.py        (needs sample_docs/; run  python make_samples.py  first)
Writes TEST_RESULTS.md. Exit code 0 only if every check passes.

Each check belongs to a group. R01-R16 are the required test cases from the Week 6 brief;
the other groups cover the RAG check, security, performance, API, UI and reporting.
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import warnings

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)

import audit  # noqa: E402
import anomaly  # noqa: E402
import classifier  # noqa: E402
import config  # noqa: E402
import database as db  # noqa: E402
import processor  # noqa: E402
import rag  # noqa: E402
import reports  # noqa: E402
import service  # noqa: E402
import storage  # noqa: E402
import workflow as wf  # noqa: E402

SAMPLES = os.path.join(HERE, "sample_docs")
MANIFEST = json.load(open(os.path.join(SAMPLES, "manifest.json")))

REQUIRED = {
    "R01": "Clean digital PDF",
    "R02": "Scanned document requiring OCR",
    "R03": "Supported document types (invoice, CV) classified and extracted",
    "R04": "Document with missing required fields",
    "R05": "Duplicate document or repeated identifier",
    "R06": "Unsupported file type",
    "R07": "Corrupted or unreadable file",
    "R08": "Low-confidence classification or extraction",
    "R09": "Arithmetic mismatch (financial fields)",
    "R10": "Invalid workflow transition",
    "R11": "Mixed-success batch processing",
    "R12": "Application restart with stored records still available",
    "R13": "AI assistant: question answered from a document",
    "R14": "AI assistant: documents do not contain enough information",
    "R15": "Review actions update status and audit history",
    "R16": "Search and filters",
}
results = []  # (group, name, ok, detail)


def check(group, name, condition, detail=""):
    ok = bool(condition)
    results.append((group, name, ok, str(detail)))
    print(("PASS" if ok else "FAIL"), group, "-", name, ("| " + str(detail)) if detail and not ok else "")


def read_sample(name):
    with open(os.path.join(SAMPLES, name), "rb") as fh:
        return fh.read()


def new_env():
    """A brand-new empty database + storage folder; caches reset."""
    tmp = tempfile.mkdtemp(prefix="docai_test_")
    config.DB_PATH = os.path.join(tmp, "documents.db")
    config.STORAGE_ROOT = os.path.join(tmp, "storage")
    db.init_db()
    rag.reset_index()
    return tmp


def make_pdf_bytes(lines, pages=1):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    for _ in range(pages):
        y = 800
        for line in lines:
            c.drawString(60, y, line)
            y -= 24
        c.showPage()
    c.save()
    return buf.getvalue()


def invoice_lines(number, company="Test Supplies Ltd", date="2025-02-01", sub="100.00", tax="10.00", total="$110.00"):
    return [company, "INVOICE", f"Invoice No: {number}", f"Date: {date}", "Bill To: Sample Customer Co",
            f"Subtotal: {sub}", f"Tax: {tax}", f"Total Amount: {total}", "Payment terms: net 30"]


def main():
    config.MAX_FILE_BYTES = 10 * 1024 * 1024
    tmp = new_env()
    ids, outcomes = {}, {}

    # =====================================================================
    # Full pipeline over the sample corpus (in processing order)
    # =====================================================================
    for e in MANIFEST["documents"]:
        res = service.upload_and_process(e["file"], read_sample(e["file"]))
        ids[e["file"]] = res["upload"].doc_id
        outcomes[e["file"]] = res["workflow"]

    def D(name):
        return db.get_document(ids[name])

    # ---- R01 clean digital PDF
    d = D("invoice_acme.pdf")
    check("R01", "Clean digital PDF is read as PDF text (no OCR) and completes automatically",
          d["text_method"] == "pdf-text" and d["status"] == wf.COMPLETED, f"{d['text_method']} {d['status']}")
    check("R01", "Clean PDF fields extracted correctly",
          d["fields"]["invoice_number"] == "INV-1001" and d["fields"]["total_amount"] == "$1,200.00"
          and d["fields"]["subtotal"] == "1,100.00" and d["fields"]["company_name"] == "ACME Trading Ltd", d["fields"])
    check("R01", "Total is the 'Total Amount' line, never the Subtotal (Week 5 bug fixed)",
          all(D(f)["fields"]["total_amount"] == next(m["fields"]["total_amount"] for m in MANIFEST["documents"] if m["file"] == f)
              for f in ("invoice_acme.pdf", "invoice_bluebird.pdf", "invoice_northwind.pdf", "invoice_harbor.pdf")))

    # ---- R02 scanned / OCR
    for f in ("scan_invoice_lakeside.png", "scan_resume_hina.png"):
        d = D(f)
        exp = next(m for m in MANIFEST["documents"] if m["file"] == f)
        check("R02", f"{f}: read with OCR, classified {exp['type']}, completes",
              d["text_method"] == "ocr" and d["doc_type"] == exp["type"] and d["status"] == wf.COMPLETED,
              f"{d['text_method']} {d['doc_type']} {d['status']} {d['review_reason']}")
        check("R02", f"{f}: OCR fields match ground truth",
              all(str(d["fields"].get(k, "")).lower() == str(v).lower() for k, v in exp["fields"].items()
                  if k != "skills") , d["fields"])
    d = D("scan_blank_unreadable.png")
    check("R02", "Blank/unreadable scan goes to review (no crash)",
          d["status"] == wf.NEEDS_REVIEW and "No readable text" in d["review_reason"], d["review_reason"])

    # ---- R03 supported types: classification and routing for the whole corpus
    wrong = [(m["file"], D(m["file"])["doc_type"], m["type"]) for m in MANIFEST["documents"]
             if D(m["file"])["doc_type"] != m["type"]]
    check("R03", f"All {len(MANIFEST['documents'])} corpus documents classified to their true type", not wrong, wrong)
    wrong = [(m["file"], D(m["file"])["status"], m["status"]) for m in MANIFEST["documents"]
             if D(m["file"])["status"] != m["status"]]
    check("R03", "All corpus documents reach the expected workflow status", not wrong, wrong)
    bad_fields = []
    for m in MANIFEST["documents"]:
        if m["type"] == "Other":
            continue
        for k, v in m["fields"].items():
            got = str(D(m["file"])["fields"].get(k, "")).strip().lower()
            if k == "skills":
                if set(got.replace(" ", "").split(",")) != set(v.replace(" ", "").split(",")):
                    bad_fields.append((m["file"], k, got, v))
            elif got != str(v).strip().lower():
                bad_fields.append((m["file"], k, got, v))
    check("R03", "Structured extraction matches ground truth for every expected field", not bad_fields, bad_fields[:5])
    check("R03", "Files stored in type folders (invoices/resumes/other)",
          "invoices" in D("invoice_acme.pdf")["stored_path"] and "resumes" in D("resume_sara.pdf")["stored_path"]
          and os.sep + "other" + os.sep in D("memo_team_meeting.pdf")["stored_path"])
    check("R03", "Results are stored in the database (fields, validation, anomalies, timings, text)",
          all(D(f)["fields"] and D(f)["validation"] and D(f)["timings"] and D(f)["extracted_text"]
              for f in ("invoice_acme.pdf", "resume_sara.pdf")))

    # ---- R04 missing required fields
    d = D("invoice_missing_total.pdf")
    check("R04", "Invoice missing total -> Needs Review, exactly that field recorded",
          d["status"] == wf.NEEDS_REVIEW and d["validation"]["missing"] == ["total_amount"], d["validation"])
    d = D("resume_missing_email.pdf")
    check("R04", "Resume missing email -> Needs Review", d["status"] == wf.NEEDS_REVIEW
          and d["validation"]["missing"] == ["email"], d["validation"])
    d = D("invoice_invalid_date.pdf")
    check("R04", "Invalid date -> Needs Review with the field named", "date" in d["validation"]["invalid"])
    d = D("invoice_zero_total.pdf")
    check("R04", "Zero total -> Needs Review", "total_amount" in d["validation"]["invalid"])

    # ---- R05 duplicates and repeated identifiers
    before = len(db.list_documents())
    dup = service.ingest("invoice_acme_copy.pdf", read_sample("invoice_acme.pdf"))
    check("R05", "Identical file re-uploaded under another name is blocked",
          (not dup.ok) and dup.code == "duplicate" and dup.duplicate_of == ids["invoice_acme.pdf"], dup.message)
    check("R05", "Duplicate creates no new record and is audited",
          len(db.list_documents()) == before
          and any(h["action"] == "Duplicate upload blocked" for h in audit.get_history(ids["invoice_acme.pdf"])))
    d = D("invoice_repeated_number.pdf")
    check("R05", "Different file reusing invoice number INV-1001 is flagged and sent to review",
          d["status"] == wf.NEEDS_REVIEW and any(a["code"] == "duplicate_identifier" for a in d["anomalies"]),
          d["anomalies"])
    d = D("resume_repeated_email.pdf")
    check("R05", "Resume reusing another resume's email is flagged",
          any(a["code"] == "duplicate_identifier" for a in d["anomalies"]), d["anomalies"])
    d = D("invoice_future_date.pdf")
    check("R05", "Future-dated invoice flagged as an anomaly", any(a["code"] == "future_date" for a in d["anomalies"]))
    d = D("invoice_huge_amount.pdf")
    check("R05", "Invoice far above the median total flagged as unusual",
          any(a["code"] == "unusual_amount" for a in d["anomalies"]), d["anomalies"])
    check("R05", "Normal invoices have no anomalies",
          all(D(f)["anomalies"] == [] for f in ("invoice_acme.pdf", "invoice_bluebird.pdf", "invoice_northwind.pdf",
                                                  "invoice_harbor.pdf", "scan_invoice_lakeside.png")))

    # ---- R06 / R07 rejected uploads
    docs_before, rej_before = len(db.list_documents()), len(db.recent_rejections(100))
    bad_results = {}
    for entry in MANIFEST["rejected_uploads"]:
        res = service.ingest(entry["file"], read_sample(entry["file"]))
        bad_results[entry["file"]] = res
        group = "R06" if entry["expected_code"] == "unsupported_type" else "R07"
        check(group, f"{entry['file']}: rejected with code '{entry['expected_code']}' and a friendly message",
              (not res.ok) and res.code == entry["expected_code"] and "Traceback" not in res.message
              and "Exception" not in res.message, f"{res.code}: {res.message}")
    check("R07", "No rejected file was stored and each rejection was logged",
          len(db.list_documents()) == docs_before
          and len(db.recent_rejections(100)) - rej_before == len(MANIFEST["rejected_uploads"]))
    # corrupt file that passes upload checks but fails while processing -> back to New, retry works
    up = service.ingest("will_vanish.pdf", make_pdf_bytes(invoice_lines("VAN-1")))
    stored = db.get_document(up.doc_id)["stored_path"]
    saved = open(stored, "rb").read()
    os.remove(stored)
    r = service.run_workflow(up.doc_id)
    d = db.get_document(up.doc_id)
    check("R07", "Stored file missing at processing time -> failed safely, status back to New, audited",
          r["outcome"] == "failed" and d["status"] == wf.NEW
          and audit.get_history(up.doc_id)[-1]["action"] == "Processing failed" and "Traceback" not in r["reason"], r)
    open(stored, "wb").write(saved)
    r = service.run_workflow(up.doc_id)
    check("R07", "After the file is restored the document can be retried successfully",
          r["outcome"] == "processed", r)

    # ---- R08 low-confidence classification / extraction
    d = D("invoice_missing_total.pdf")
    check("R08", "Low extraction quality is measured: field completeness 75% for the invoice missing a total",
          d["validation"]["completeness"] == 0.75, d["validation"]["completeness"])
    check("R08", "Rule-based classifier stores no confidence (never invented)", D("invoice_acme.pdf")["confidence"] is None)
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    import joblib
    texts = ["invoice no total amount due bill to tax subtotal payment terms",
             "invoice number date company total due tax subtotal",
             "purchase order invoice subtotal amount due payment terms net 30",
             "invoice bill to total tax due date amount",
             "resume skills education experience email phone",
             "curriculum vitae skills work experience education projects",
             "skills python sql education objective summary references",
             "work experience education skills certifications cv email",
             "meeting memo roadmap friday team update laptops",
             "agenda minutes discussion action items team meeting",
             "newsletter announcement office holiday schedule",
             "memo to staff about parking and office hours"]
    labels = ["Invoice"] * 4 + ["Resume"] * 4 + ["Other"] * 4
    model_path = os.path.join(tmp, "model.joblib")
    joblib.dump(make_pipeline(TfidfVectorizer(), LogisticRegression(max_iter=1000, C=10)).fit(texts, labels), model_path)
    old_model, old_thr = config.MODEL_PATH, config.CONFIDENCE_THRESHOLD
    config.MODEL_PATH = model_path
    classifier.reset_model_cache()
    try:
        config.CONFIDENCE_THRESHOLD = 0.0
        a = service.upload_and_process("model_ok.pdf", make_pdf_bytes(invoice_lines("MOD-1")))
        da = db.get_document(a["upload"].doc_id)
        check("R08", "A real trained model supplies a probability that is stored with the document",
              da["classifier"] == "tfidf-model" and isinstance(da["confidence"], float) and 0 < da["confidence"] <= 1
              and da["doc_type"] == "Invoice", f"{da['classifier']} {da['confidence']} {da['doc_type']}")
        config.CONFIDENCE_THRESHOLD = 0.999
        b = service.upload_and_process("model_low.pdf", make_pdf_bytes(invoice_lines("MOD-2")))
        db_ = db.get_document(b["upload"].doc_id)
        check("R08", "Classification confidence below the threshold -> Needs Review with the reason",
              db_["status"] == wf.NEEDS_REVIEW and "Low classification confidence" in (db_["review_reason"] or ""),
              f"{db_['confidence']} {db_['review_reason']}")
        dec_hi = wf.decide("Invoice", {"valid": True, "missing": [], "invalid": {}}, 0.95, True, [], 0.6)
        dec_lo = wf.decide("Invoice", {"valid": True, "missing": [], "invalid": {}}, 0.40, True, [], 0.6)
        check("R08", "Decision engine: 0.95 approves, 0.40 goes to review (threshold 0.60)",
              dec_hi.next_status == wf.APPROVED and dec_lo.next_status == wf.NEEDS_REVIEW)
    finally:
        config.MODEL_PATH, config.CONFIDENCE_THRESHOLD = old_model, old_thr
        classifier.reset_model_cache()

    # ---- R09 arithmetic
    d = D("invoice_arithmetic_mismatch.pdf")
    check("R09", "Subtotal + tax != total is flagged and sent to review",
          d["status"] == wf.NEEDS_REVIEW and any(a["code"] == "arithmetic_mismatch" for a in d["anomalies"]),
          d["anomalies"])
    f = {"subtotal": "100.00", "tax": "10.00", "total_amount": "110.00"}
    check("R09", "Exact match is not flagged", anomaly.detect(0, "Invoice", {**f, "invoice_number": "Not Found", "date": "Not Found"}) == [])
    check("R09", "Difference within the 0.01 tolerance is not flagged",
          not any(a["code"] == "arithmetic_mismatch" for a in anomaly.detect(0, "Invoice", {**f, "total_amount": "110.01"})))
    check("R09", "Check is skipped when tax is Not Found (cannot be verified)",
          not any(a["code"] == "arithmetic_mismatch" for a in anomaly.detect(0, "Invoice", {**f, "tax": "Not Found", "total_amount": "999"})))

    # ---- R10 invalid transitions
    attempts = [(ids["invoice_acme.pdf"], wf.REJECTED), (ids["invoice_acme.pdf"], wf.NEEDS_REVIEW),
                (ids["invoice_acme.pdf"], wf.PROCESSING), (ids["invoice_missing_total.pdf"], wf.COMPLETED),
                (ids["invoice_missing_total.pdf"], wf.NEW)]
    blocked = []
    for doc_id, target in attempts:
        try:
            wf.change_status(doc_id, target, "test")
            blocked.append(False)
        except wf.InvalidTransition:
            blocked.append(True)
    check("R10", "Completed->Rejected/Needs Review/Processing and Needs Review->Completed/New are all blocked", all(blocked))
    check("R10", "Blocked attempts leave the status unchanged and are written to the audit log",
          D("invoice_acme.pdf")["status"] == wf.COMPLETED
          and any(h["action"].startswith("Blocked") for h in audit.get_history(ids["invoice_acme.pdf"])))
    r = service.run_workflow(ids["invoice_acme.pdf"])
    check("R10", "Re-running the workflow on a completed document skips it (stored results reused)",
          r["outcome"] == "skipped", r)

    # ---- RAG: chunking and embeddings use the intended text
    bad_chunks = []
    for name in ("invoice_acme.pdf", "resume_sara.pdf", "scan_invoice_lakeside.png", "memo_team_meeting.pdf"):
        d = D(name)
        chunk_lines = {ln for c in db.get_chunks(d["id"]) for ln in c["text"].splitlines()}
        doc_lines = {ln.strip() for ln in d["extracted_text"].splitlines() if ln.strip()}
        if not doc_lines <= chunk_lines:
            bad_chunks.append(name)
    check("RAG", "Stored chunks contain every line of the document's extracted text (and nothing else)", not bad_chunks, bad_chunks)
    check("RAG", "Chunk text comes from OCR for scanned documents",
          any("LP-905" in c["text"] for c in db.get_chunks(ids["scan_invoice_lakeside.png"])))
    check("RAG", "Unreadable document produces no chunks", db.get_chunks(ids["scan_blank_unreadable.png"]) == [])

    lookups = [("What is the total amount on invoice HL-310?", "invoice_harbor.pdf", "$800.00"),
               ("What is the total amount on invoice NW-2043?", "invoice_northwind.pdf", "$2,530.00"),
               ("What is the total amount on invoice BB-77?", "invoice_bluebird.pdf", "$500.00"),
               ("What is the total on invoice LP-905?", "scan_invoice_lakeside.png", "$330.00"),
               ("What skills does Sara Khan have?", "resume_sara.pdf", "Machine Learning"),
               ("What is Ali Raza's email address?", "resume_ali.pdf", "ali.raza@mail.org"),
               ("What is the phone number of Hina Malik?", "scan_resume_hina.png", "+92 333 4445566")]
    top_ok, answer_ok, detail = 0, 0, []
    for q, doc_name, expect in lookups:
        res = rag.ask(q)
        src_ok = res["grounded"] and res["sources"] and res["sources"][0]["filename"] == doc_name
        ans_ok = res["grounded"] and expect.lower() in res["answer"].lower()
        top_ok += bool(src_ok)
        answer_ok += bool(ans_ok)
        if not (src_ok and ans_ok):
            detail.append((q, res["answer"][:80]))
    check("RAG", f"Semantic retrieval returns the right document first ({top_ok}/{len(lookups)})", top_ok == len(lookups), detail)
    check("RAG", f"Answers contain the correct value ({answer_ok}/{len(lookups)})", answer_ok == len(lookups), detail)

    # ---- R13 answerable question with sources
    res = rag.ask("What is the date of invoice HL-310 and what is its total?")
    check("R13", "Answer is grounded and quotes the document lines",
          res["grounded"] and "2025-07-08" in res["answer"] and "$800.00" in res["answer"], res["answer"])
    check("R13", "Answer shows supporting document, status, chunk and score",
          res["sources"] and {"filename", "document_id", "status", "chunk_index", "score", "snippet"} <= set(res["sources"][0]))
    res = rag.ask("What are the total amounts of the ACME Trading and Bluebird Supplies invoices?")
    names = {s["filename"] for s in res["sources"]}
    check("R13", "Question needing more than one document uses both",
          {"invoice_acme.pdf", "invoice_bluebird.pdf"} <= names and "$1,200.00" in res["answer"] and "$500.00" in res["answer"],
          res["answer"])
    res = rag.ask("Which documents mention Python?")
    check("R13", "'Which documents...' question lists several documents",
          len({s["filename"] for s in res["sources"]}) >= 3 and res["grounded"], res["answer"])

    # ---- R14 not enough information
    unanswerable = ["What is the warranty period for the product?", "Who is the president of France?",
                    "What is the refund policy?", "How many employees does ACME have?"]
    qa_before = len(db.recent_questions(1000, only_unanswered=True))
    outs = [rag.ask(q) for q in unanswerable]
    check("R14", "Out-of-scope questions get the 'not enough information' answer with no sources",
          all((not o["grounded"]) and o["answer"] == rag.NOT_ENOUGH and o["sources"] == [] for o in outs),
          [(q, o["top_score"], o["coverage"]) for q, o in zip(unanswerable, outs)])
    check("R14", "Every unanswered question is recorded, not hidden",
          len(db.recent_questions(1000, only_unanswered=True)) - qa_before == len(unanswerable))
    check("R14", "Too-short question is handled", not rag.ask("hi")["grounded"])
    builds = rag.stats["builds"]
    for q in ("What is the total amount on invoice HL-310?", "What skills does Sara Khan have?", "Who is the president of France?"):
        rag.ask(q)
    check("RAG", "Search index is reused between questions (not rebuilt for each)", rag.stats["builds"] == builds)

    # =====================================================================
    # Search / filters / reporting
    # =====================================================================
    check("R16", "Search by company", any(d["id"] == ids["invoice_acme.pdf"] for d in db.list_documents(search="ACME")))
    check("R16", "Search by invoice number finds every use of INV-1001",
          {d["id"] for d in db.list_documents(search="INV-1001")} == {ids["invoice_acme.pdf"], ids["invoice_repeated_number.pdf"]})
    check("R16", "Search by email", len(db.list_documents(search="sara.khan@example.com")) == 2)
    check("R16", "Search by person name", len(db.list_documents(search="Hina")) == 1)
    check("R16", "Status filter", all(d["status"] == wf.NEEDS_REVIEW for d in db.list_documents(status=wf.NEEDS_REVIEW)))
    check("R16", "Type filter", all(d["doc_type"] == "Resume" for d in db.list_documents(doc_type="Resume")))
    check("R16", "Combined filter + search",
          all(d["doc_type"] == "Invoice" and d["status"] == wf.COMPLETED
              for d in db.list_documents(status=wf.COMPLETED, doc_type="Invoice", search="Ltd")))
    check("R16", "Latest action and timestamp shown for every document",
          all(d["last_action"] and d["last_action_at"] for d in db.list_documents()))
    hostile = db.list_documents(search="'; DROP TABLE documents;--")
    check("SEC", "SQL injection attempt in search is harmless", hostile == [] and len(db.list_documents()) > 0)
    csv_text = reports.documents_csv()
    check("R16", "CSV report has one row per document", csv_text.count("\n") == len(db.list_documents()) + 1)

    # ---- dashboard numbers reconcile with the data
    m = db.metrics()
    docs = db.list_documents()
    count = lambda s: sum(d["status"] == s for d in docs)  # noqa: E731
    check("DASH", "Totals by status/type add up to the document count",
          m["total"] == len(docs) == sum(m["by_status"].values()) == sum(m["by_type"].values()))
    check("DASH", "Approved/rejected/completed/needs-review counts match stored statuses",
          (m["approved"], m["rejected"], m["completed"], m["needs_review"]) ==
          (count(wf.APPROVED), count(wf.REJECTED), count(wf.COMPLETED), count(wf.NEEDS_REVIEW)))
    check("DASH", "Anomaly count matches documents with anomalies", m["documents_with_anomalies"] == sum(bool(d["anomalies"]) for d in docs))
    check("DASH", "Validation counts match", m["validation_failed"] == sum(
        d["doc_type"] in ("Invoice", "Resume") and not d["validation"].get("valid", True) for d in docs))
    check("DASH", "Duplicate and rejected-upload counts match what was done",
          m["duplicates_blocked"] == 1 and m["rejected_uploads"] == len(MANIFEST["rejected_uploads"]))
    check("DASH", "Failed count is zero after the retry succeeded", m["failed"] == 0, m["failed"])
    check("DASH", "Processing times and slowest stage are measured",
          m["avg_processing_ms"] is not None and m["slowest_stage"] in m["stage_avg_ms"], m["stage_avg_ms"])
    check("DASH", "Recent activity available", len(audit.get_recent(10)) == 10)

    # =====================================================================
    # R15 review actions (mutating, so after the read-only checks)
    # =====================================================================
    reviewable = ids["invoice_missing_total.pdf"]
    wf.approve(reviewable, "Total confirmed on paper copy")
    hist = audit.get_history(reviewable)
    check("R15", "Approve -> Approved -> Completed, reviewer note and review reason cleared",
          D("invoice_missing_total.pdf")["status"] == wf.COMPLETED and D("invoice_missing_total.pdf")["review_reason"] is None
          and [h["action"] for h in hist][-2:] == ["Reviewer approved", "Workflow completed"]
          and hist[-2]["note"] == "Total confirmed on paper copy", [h["action"] for h in hist])
    target = ids["resume_missing_email.pdf"]
    try:
        wf.reject(target, "   ")
        empty_ok = False
    except ValueError:
        empty_ok = True
    check("R15", "Reject without a reason is refused and nothing changes", empty_ok and D("resume_missing_email.pdf")["status"] == wf.NEEDS_REVIEW)
    wf.reject(target, "Applicant record incomplete")
    h = audit.get_history(target)[-1]
    check("R15", "Reject updates status and audit with the reason",
          D("resume_missing_email.pdf")["status"] == wf.REJECTED and h["action"] == "Reviewer rejected"
          and h["old_status"] == wf.NEEDS_REVIEW and h["new_status"] == wf.REJECTED and "incomplete" in h["note"], h)
    check("R15", "Audit history is complete and in order for a processed document",
          [x["action"] for x in audit.get_history(ids["invoice_acme.pdf"])][:6] ==
          ["Uploaded", "Processing started", "Classified & extracted", "Validated", "Anomaly check", "Auto-approved by rules"])
    res = rag.ask("What are Omar Farooq's skills?")
    check("RAG", "Rejected documents are excluded from assistant answers",
          not any(s["document_id"] == target for s in res["sources"]), res["answer"])

    # =====================================================================
    # R11 mixed-success batch
    # =====================================================================
    new_env()
    a = service.ingest("b_good_invoice.pdf", make_pdf_bytes(invoice_lines("BATCH-1"))).doc_id
    b = service.ingest("b_missing_total.pdf", make_pdf_bytes(["Q Corp Inc", "INVOICE", "Invoice No: BATCH-2",
                                                              "Date: 2025-02-01", "Bill To: X Co", "Payment terms: net 30"])).doc_id
    c = service.ingest("b_vanishing.pdf", make_pdf_bytes(invoice_lines("BATCH-3"))).doc_id
    os.remove(db.get_document(c)["stored_path"])
    d_ = service.ingest("b_resume.pdf", make_pdf_bytes(["Nadia Ahmed", "Email: nadia@example.com", "Phone: +92 300 7654321",
                                                       "Skills: Python, SQL", "Education: BS", "Work Experience: intern"])).doc_id
    e_ = service.ingest("b_already_done.pdf", make_pdf_bytes(invoice_lines("BATCH-5"))).doc_id
    service.run_workflow(e_)
    batch = service.run_batch([a, b, c, 424242, d_, e_, a])  # includes a missing id and a repeated id
    by_id = {r["id"]: r for r in batch["results"]}
    check("R11", "Batch counts: 2 completed, 1 needs review, 2 failed, 1 skipped",
          (batch["processed"], batch["review"], batch["failed"], batch["skipped"]) == (2, 1, 2, 1), batch)
    check("R11", "One result per distinct id (repeated id processed once)", len(batch["results"]) == 6, len(batch["results"]))
    check("R11", "Documents after a failure were still processed", by_id[d_]["outcome"] == "processed" and by_id[a]["outcome"] == "processed")
    check("R11", "Failed documents explain why in plain words (no tracebacks)",
          all(r["reason"] and "Traceback" not in r["reason"] for r in batch["results"] if r["outcome"] == "failed"),
          [r["reason"] for r in batch["results"] if r["outcome"] == "failed"])
    check("R11", "Failed document returned to New (retryable); batch DB state consistent",
          db.get_document(c)["status"] == wf.NEW and db.get_document(b)["status"] == wf.NEEDS_REVIEW)

    # larger batch: stability and speed
    ids_big = [service.ingest(f"bulk_{i}.pdf", make_pdf_bytes(invoice_lines(f"BULK-{i}", total=f"${110 + i}.00", sub=f"{100 + i}.00")
                                                              )).doc_id for i in range(40)]
    t0 = time.perf_counter()
    big = service.run_batch(ids_big)
    secs = time.perf_counter() - t0
    check("PERF", f"Batch of 40 documents completes with no failures ({secs:.1f}s, {40 / secs:.1f} docs/s)",
          big["failed"] == 0 and big["processed"] + big["review"] == 40, big)

    # =====================================================================
    # Performance behaviours
    # =====================================================================
    new_env()
    up = service.upload_and_process("perf.pdf", make_pdf_bytes(invoice_lines("PERF-1")))
    did = up["upload"].doc_id
    d1 = db.get_document(did)
    n_audit = len(audit.get_history(did))
    r = service.run_workflow(did)
    d2 = db.get_document(did)
    check("PERF", "Valid stored results are reused: second run is skipped, nothing recomputed",
          r["outcome"] == "skipped" and d2["processing_ms"] == d1["processing_ms"] and d2["fields"] == d1["fields"]
          and [h["action"] for h in audit.get_history(did)][n_audit:] == ["Reprocessing skipped"])
    same_bytes = make_pdf_bytes(invoice_lines("PERF-2"))
    first_up, second_up = service.ingest("one.pdf", same_bytes), service.ingest("two.pdf", same_bytes)
    check("PERF", "Document hash blocks a second copy before any processing happens",
          first_up.ok and second_up.code == "duplicate" and second_up.duplicate_of == first_up.doc_id)
    scan = read_sample("scan_invoice_lakeside.png")
    hits0 = processor.cache_stats["hits"]
    t0 = time.perf_counter(); processor.read_document(scan, "x.png"); first = time.perf_counter() - t0
    t0 = time.perf_counter(); processor.read_document(scan, "x.png"); second = time.perf_counter() - t0
    check("PERF", f"OCR result is cached by content hash (first {first * 1000:.0f} ms, repeat {second * 1000:.2f} ms)",
          processor.cache_stats["hits"] == hits0 + 1 and second < first)
    check("PERF", "Every processed document records time per pipeline stage",
          {"read_file", "text_extraction", "classification", "field_extraction", "validation", "anomaly_check",
           "ai_indexing", "total"} <= set(d1["timings"]), d1["timings"])

    # =====================================================================
    # Restart
    # =====================================================================
    tmp_restart = new_env()
    for name in ("invoice_harbor.pdf", "resume_sara.pdf", "scan_invoice_lakeside.png"):
        service.upload_and_process(name, read_sample(name))
    stuck = service.ingest("stuck.pdf", make_pdf_bytes(invoice_lines("STUCK-1"))).doc_id
    wf.change_status(stuck, wf.PROCESSING, "Processing started")  # simulate a crash mid-processing
    before = db.metrics()
    code = ("import json, sys\nsys.path.insert(0, '.')\nimport audit, config, database as db, rag, service\n"
            "db.init_db()\nrec = service.recover_interrupted()\nm = db.metrics()\n"
            "r = rag.ask('What is the total amount on invoice HL-310?')\n"
            "print('RESULT' + json.dumps({'total': m['total'], 'completed': m['completed'], 'grounded': r['grounded'],"
            " 'answer': r['answer'], 'recovered': rec, 'stuck_status': db.get_document(%d)['status']}))\n" % stuck)
    env = {**os.environ, "DB_PATH": config.DB_PATH, "STORAGE_ROOT": config.STORAGE_ROOT}
    proc = subprocess.run([sys.executable, "-W", "ignore", "-c", code], env=env, cwd=HERE, capture_output=True, text=True, timeout=120)
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT")), None)
    out = json.loads(line[6:]) if line else {}
    check("R12", "New process sees the same stored records",
          out.get("total") == before["total"] and out.get("completed") == before["completed"], (out, proc.stderr[-300:]))
    check("R12", "AI assistant works in the new process (index rebuilt from stored chunks)",
          out.get("grounded") and "$800.00" in out.get("answer", ""), out)
    check("R12", "Document interrupted mid-processing is recovered to New and can be retried",
          out.get("recovered") == 1 and out.get("stuck_status") == wf.NEW
          and service.run_workflow(stuck)["outcome"] == "processed", out)
    rag.reset_index()
    classifier.reset_model_cache()
    check("R12", "Search, files and audit history survive restart",
          len(db.list_documents(search="HL-310")) == 1 and len(audit.get_history(1)) >= 5
          and os.path.exists(db.get_document(1)["stored_path"]))

    # =====================================================================
    # Security
    # =====================================================================
    new_env()
    os.makedirs(config.STORAGE_ROOT, exist_ok=True)
    for bad in ("../../etc/passwd", "/etc/passwd", os.path.join(config.STORAGE_ROOT, "..", "documents.db")):
        try:
            storage.read_file(bad)
            denied = False
        except storage.StorageError as exc:
            denied = exc.code == "path_denied"
        check("SEC", f"Directory traversal / outside path refused: {bad}", denied)
    link = os.path.join(config.STORAGE_ROOT, "sneaky_link")
    os.symlink("/etc/hostname", link)
    try:
        storage.read_file(link)
        denied = False
    except storage.StorageError as exc:
        denied = exc.code == "path_denied"
    check("SEC", "Symlink pointing outside storage is refused", denied)
    check("SEC", "Hostile filenames are sanitised",
          storage.safe_filename("../../evil name;rm -rf.pdf") == "evil_name_rm_-rf.pdf"
          and storage.safe_filename("C:\\Users\\x\\inv.PDF") == "inv.pdf" and storage.safe_filename("....pdf") == "pdf",
          [storage.safe_filename(x) for x in ("../../evil name;rm -rf.pdf", "C:\\Users\\x\\inv.PDF", "....pdf")])
    up = service.ingest("../../../tmp/evil name.pdf", make_pdf_bytes(invoice_lines("SEC-1")))
    path = os.path.realpath(db.get_document(up.doc_id)["stored_path"])
    check("SEC", "Upload with a traversal filename is stored inside the storage root under a generated name",
          up.ok and path.startswith(os.path.realpath(config.STORAGE_ROOT) + os.sep) and ".." not in os.path.basename(path))
    old = config.MAX_FILE_BYTES
    config.MAX_FILE_BYTES = 500
    res = service.ingest("big.pdf", make_pdf_bytes(invoice_lines("SEC-2")))
    config.MAX_FILE_BYTES = old
    check("SEC", "Oversized file rejected (too_large)", res.code == "too_large", res.message)
    res = service.ingest("fake.pdf", b"MZ" + b"\x00" * 300)
    check("SEC", "Executable renamed to .pdf rejected by content check", res.code == "invalid_content", res.message)
    old = config.MAX_PDF_PAGES
    config.MAX_PDF_PAGES = 2
    res = service.ingest("long.pdf", make_pdf_bytes(invoice_lines("SEC-3"), pages=3))
    config.MAX_PDF_PAGES = old
    check("SEC", "PDF over the page limit rejected", res.code == "too_many_pages", res.message)
    import pymupdf
    enc_doc = pymupdf.open()
    enc_doc.new_page().insert_text((72, 72), "secret invoice text for encryption test")
    enc = enc_doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o")
    res = service.ingest("locked.pdf", enc)
    check("SEC", "Password-protected PDF rejected with a clear message", (not res.ok) and "password" in res.message.lower(), res.message)
    old = config.MAX_IMAGE_PIXELS
    config.MAX_IMAGE_PIXELS = 1000
    res = service.ingest("huge.png", read_sample("scan_invoice_lakeside.png"))
    config.MAX_IMAGE_PIXELS = old
    check("SEC", "Oversized image (pixel bomb guard) rejected", not res.ok and res.code in ("too_large_image", "corrupt"), res.message)
    src = {f: open(os.path.join(HERE, f), encoding="utf-8").read() for f in os.listdir(HERE) if f.endswith(".py")}
    leaks = [f for f, t in src.items() if f != "test_e2e.py" and ("sk-ant" in t or "password=" in t.lower())]
    check("SEC", "No secrets in source code; settings come from environment / .env", not leaks
          and "API_KEY = os.environ.get" in src["config.py"], leaks)
    gi = open(os.path.join(HERE, ".gitignore")).read()
    check("SEC", ".env, database and storage are git-ignored and .env.example exists",
          all(x in gi for x in (".env", "data/")) and os.path.exists(os.path.join(HERE, ".env.example"))
          and not os.path.exists(os.path.join(HERE, ".env")))
    tracebacks = [f for f, t in src.items() if f in ("app.py", "api.py", "service.py") and "traceback.print" in t]
    check("SEC", "User-facing code never prints raw tracebacks", not tracebacks)

    # =====================================================================
    # API
    # =====================================================================
    from fastapi.testclient import TestClient
    import api
    new_env()
    config.API_KEY = ""
    with TestClient(api.app) as client:
        check("API", "GET /health -> 200", client.get("/health").status_code == 200)
        r = client.post("/documents", files={"file": ("invoice_harbor.pdf", read_sample("invoice_harbor.pdf"), "application/pdf")})
        body = r.json()
        check("API", "POST /documents -> 201 with processed document and workflow outcome",
              r.status_code == 201 and body["workflow"]["outcome"] == "processed" and body["document"]["status"] == wf.COMPLETED, r.text[:200])
        check("API", "Responses never expose internal file paths", "stored_path" not in r.text and config.STORAGE_ROOT not in r.text)
        doc_id = body["document"]["id"]
        r = client.post("/documents", files={"file": ("again.pdf", read_sample("invoice_harbor.pdf"), "application/pdf")})
        check("API", "Duplicate upload -> 409 with existing id",
              r.status_code == 409 and r.json()["detail"]["existing_document_id"] == doc_id, r.text[:200])
        r = client.post("/documents", files={"file": ("notes.txt", b"hello", "text/plain")})
        check("API", "Unsupported type -> 415", r.status_code == 415, r.text[:150])
        r = client.post("/documents", files={"file": ("fake.pdf", b"not a pdf at all", "application/pdf")})
        check("API", "Corrupt/fake content -> 422", r.status_code == 422, r.text[:150])
        config.MAX_FILE_BYTES = 500
        r = client.post("/documents", files={"file": ("big.pdf", read_sample("invoice_acme.pdf"), "application/pdf")})
        config.MAX_FILE_BYTES = 10 * 1024 * 1024
        check("API", "Oversized upload -> 413", r.status_code == 413, r.text[:150])
        r = client.post("/documents")
        check("API", "Missing file -> 422 validation message", r.status_code == 422)
        r = client.get(f"/documents/{doc_id}")
        check("API", "GET /documents/{id} -> detail with history and timings",
              r.status_code == 200 and len(r.json()["history"]) >= 5 and "total" in r.json()["timings_ms"])
        check("API", "GET unknown id -> 404", client.get("/documents/99999").status_code == 404)
        check("API", "GET /documents lists and searches", client.get("/documents?q=Harbor").json()["count"] == 1)
        check("API", "Invalid status filter -> 422", client.get("/documents?status=bogus").status_code == 422)
        r = client.post("/documents?process=false", files={"file": ("n.pdf", make_pdf_bytes(invoice_lines("API-9", total="$999.00")), "application/pdf")})
        new_id = r.json()["document"]["id"]
        check("API", "Upload with process=false leaves the document New", r.json()["document"]["status"] == wf.NEW)
        check("API", "POST /documents/{id}/process runs the workflow", client.post(f"/documents/{new_id}/process").json()["outcome"] in ("processed", "review"))
        check("API", "Approve on a completed document -> 409", client.post(f"/documents/{doc_id}/approve", json={}).status_code == 409)
        r = client.post("/documents", files={"file": ("m.pdf", make_pdf_bytes(["Delta Works Inc", "INVOICE", "Invoice No: API-77", "Date: 2025-01-02", "Bill To: X Co"]), "application/pdf")})
        review_id = r.json()["document"]["id"]
        check("API", "Reject with empty reason -> 422", client.post(f"/documents/{review_id}/reject", json={"reason": ""}).status_code == 422)
        check("API", "Reject without body -> 422", client.post(f"/documents/{review_id}/reject").status_code == 422)
        r = client.post(f"/documents/{review_id}/reject", json={"reason": "Incomplete invoice"})
        check("API", "Reject with reason -> 200 Rejected", r.status_code == 200 and r.json()["status"] == wf.REJECTED, r.text[:150])
        r = client.post("/ask", json={"question": "What is the total amount on invoice HL-310?"})
        check("API", "POST /ask -> grounded answer with sources", r.status_code == 200 and r.json()["grounded"] and r.json()["sources"], r.text[:150])
        r = client.post("/ask", json={"question": "What is the capital of Mars?"})
        check("API", "POST /ask unanswerable -> says not enough information", r.status_code == 200 and not r.json()["grounded"])
        check("API", "POST /ask with too-short question -> 422", client.post("/ask", json={"question": "hi"}).status_code == 422)
        check("API", "GET /metrics -> 200", client.get("/metrics").json()["total"] >= 3)
        check("API", "GET /reports/documents.csv -> CSV", client.get("/reports/documents.csv").text.startswith("id,filename"))
        config.API_KEY = "test-secret"
        check("API", "With API_KEY set: missing key -> 401", client.get("/documents").status_code == 401)
        check("API", "With API_KEY set: wrong key -> 401", client.get("/documents", headers={"X-API-Key": "nope"}).status_code == 401)
        check("API", "With API_KEY set: correct key -> 200", client.get("/documents", headers={"X-API-Key": "test-secret"}).status_code == 200)
        check("API", "With API_KEY set: /health stays open", client.get("/health").status_code == 200)
        check("API", "With API_KEY set: upload and review endpoints are protected",
              client.post("/ask", json={"question": "anything here"}).status_code == 401
              and client.post(f"/documents/{doc_id}/approve", json={}).status_code == 401)
        config.API_KEY = ""

    # =====================================================================
    # UI smoke (Streamlit pages run headlessly)
    # =====================================================================
    from streamlit.testing.v1 import AppTest
    ui_tmp = new_env()
    for e in MANIFEST["documents"][:8] + MANIFEST["documents"][11:13]:
        service.upload_and_process(e["file"], read_sample(e["file"]))
    rag.ask("What is the total amount on invoice INV-1001?")
    rag.ask("What is the refund policy?")
    at = AppTest.from_file("app.py", default_timeout=90).run()
    check("UI", "App starts without errors", not at.exception, [str(x.value) for x in at.exception])
    for page in ["Upload", "Review Queue", "Batch Processing", "Search & Filters", "AI Assistant", "Dashboard"]:
        at.sidebar.radio[0].set_value(page).run()
        check("UI", f"Page '{page}' renders without errors", not at.exception, [str(x.value) for x in at.exception])
    at.sidebar.radio[0].set_value("AI Assistant").run()
    at.text_input[0].set_value("What is the total amount on invoice HL-310?")
    at.button[0].click().run()
    check("UI", "AI Assistant page shows an answer and sources", not at.exception and len(at.success) >= 1 and len(at.dataframe) >= 1)
    at.text_input[0].set_value("What is the warranty period?")
    at.button[0].click().run()
    check("UI", "AI Assistant page shows a clear 'not enough information' warning", len(at.warning) >= 1 and rag.NOT_ENOUGH in at.warning[0].value)
    at.sidebar.radio[0].set_value("Review Queue").run()
    queue = db.list_documents(status=wf.NEEDS_REVIEW)
    if queue:
        target = queue[0]["id"]
        next(b for b in at.button if b.key == f"ap_{target}").click().run()
        check("UI", "Approve button in the review queue completes the document and logs it",
              db.get_document(target)["status"] == wf.COMPLETED and audit.get_history(target)[-1]["action"] == "Workflow completed")
        q2 = db.list_documents(status=wf.NEEDS_REVIEW)
        if q2:
            t2 = q2[0]["id"]
            at.sidebar.radio[0].set_value("Review Queue").run()
            next(b for b in at.button if b.key == f"rj_{t2}").click().run()
            check("UI", "Reject without a reason shows an error and changes nothing",
                  len(at.error) >= 1 and db.get_document(t2)["status"] == wf.NEEDS_REVIEW)
            at.text_input(key=f"note_{t2}").set_value("Not a valid document")
            next(b for b in at.button if b.key == f"rj_{t2}").click().run()
            check("UI", "Reject with a reason rejects the document", db.get_document(t2)["status"] == wf.REJECTED)

    write_report()


def write_report():
    passed = sum(1 for _, _, ok, _ in results if ok)
    lines = ["# End-to-End Test Results", "",
             f"**{passed} / {len(results)} checks passed.** Generated by `python test_e2e.py` "
             f"on {time.strftime('%Y-%m-%d %H:%M')} (local time of the machine that ran it).", "",
             "## Required test cases from the Week 6 brief", "",
             "| # | Required test case | Checks passed | Result |", "|---|---|---|---|"]
    for code, title in REQUIRED.items():
        group = [r for r in results if r[0] == code]
        ok = sum(1 for r in group if r[2])
        lines.append(f"| {code} | {title} | {ok} / {len(group)} | {'PASS' if group and ok == len(group) else 'FAIL'} |")
    other = {"RAG": "AI assistant & RAG check", "SEC": "Security", "PERF": "Performance", "DASH": "Dashboard figures",
             "API": "REST API", "UI": "Streamlit pages"}
    lines += ["", "## Other areas", "", "| Area | Checks passed | Result |", "|---|---|---|"]
    for code, title in other.items():
        group = [r for r in results if r[0] == code]
        ok = sum(1 for r in group if r[2])
        lines.append(f"| {title} | {ok} / {len(group)} | {'PASS' if group and ok == len(group) else 'FAIL'} |")
    lines += ["", "## Every check", "", "| Group | Check | Result | Detail (shown when failed) |", "|---|---|---|---|"]
    for group, name, ok, detail in results:
        lines.append(f"| {group} | {name.replace('|', '/')} | {'PASS' if ok else 'FAIL'} | {'' if ok else detail.replace('|', '/')[:200]} |")
    with open(os.path.join(HERE, "TEST_RESULTS.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"\n{passed}/{len(results)} checks passed -> TEST_RESULTS.md")
    raise SystemExit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
