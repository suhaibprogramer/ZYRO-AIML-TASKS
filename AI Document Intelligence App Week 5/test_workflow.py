"""Automated reliability & failure tests for the Week 5 workflow.

Run:  python test_workflow.py
Writes TEST_RESULTS.md with a pass/fail table (evidence for submission).
"""
import os
import shutil
import tempfile

import audit
import classifier
import database as db
import service
import storage
import validator
import workflow as wf

SAMPLES = "sample_docs"
results = []


def check(scenario, condition, detail=""):
    results.append((scenario, bool(condition), detail))
    print(("PASS" if condition else "FAIL"), "-", scenario, ("| " + detail) if detail else "")


def sample(name):
    with open(os.path.join(SAMPLES, name), "rb") as fh:
        return name, fh.read()


def fresh():
    tmp = tempfile.mkdtemp()
    dbp, root = os.path.join(tmp, "t.db"), os.path.join(tmp, "storage")
    db.init_db(dbp)
    return tmp, dbp, root


def upload_and_run(name, dbp, root):
    n, data = sample(name)
    up = service.ingest(n, data, dbp, root)
    assert up.ok, up.message
    return up.doc_id, service.run_workflow(up.doc_id, dbp, root)


def main():
    tmp, dbp, root = fresh()

    # 1 normal invoice / resume -> auto completed
    i1, r1 = upload_and_run("invoice_normal.pdf", dbp, root)
    check("1a Normal invoice completes automatically", r1["outcome"] == "processed"
          and db.get_document(i1, dbp)["status"] == wf.COMPLETED, r1["reason"])
    i2, r2 = upload_and_run("resume_normal.pdf", dbp, root)
    check("1b Normal resume completes automatically", r2["outcome"] == "processed"
          and db.get_document(i2, dbp)["status"] == wf.COMPLETED, r2["reason"])
    i2b, r2b = upload_and_run("invoice_second.pdf", dbp, root)
    check("1c Second invoice (different date/total labels) completes", r2b["outcome"] == "processed", r2b["reason"])
    i2c, r2c = upload_and_run("resume_second.pdf", dbp, root)
    check("1d Second resume completes", r2c["outcome"] == "processed", r2c["reason"])

    # audit trail of a completed document
    actions = [h["action"] for h in audit.get_history(i1, dbp)]
    check("1e Audit log has Uploaded -> Processing -> Auto-approved -> Completed",
          all(a in actions for a in ["Uploaded", "Processing started", "Auto-approved by rules",
                                     "Workflow completed"]), " | ".join(actions))
    check("1f Files moved into type folders",
          "invoices" in db.get_document(i1, dbp)["stored_path"]
          and "resumes" in db.get_document(i2, dbp)["stored_path"])

    # 2 missing required fields
    i3, r3 = upload_and_run("invoice_missing_total.pdf", dbp, root)
    d3 = db.get_document(i3, dbp)
    check("2a Invoice missing total -> Needs Review", d3["status"] == wf.NEEDS_REVIEW, d3["review_reason"])
    check("2b Exactly the failed field is recorded", d3["validation"]["missing"] == ["total_amount"],
          str(d3["validation"]["missing"]))
    i4, r4 = upload_and_run("resume_missing_email.pdf", dbp, root)
    d4 = db.get_document(i4, dbp)
    check("2c Resume missing email -> Needs Review", d4["status"] == wf.NEEDS_REVIEW
          and "email" in d4["validation"]["missing"], d4["review_reason"])

    # 3 unreadable / scanned
    i5, r5 = upload_and_run("unreadable_blank.png", dbp, root)
    d5 = db.get_document(i5, dbp)
    check("3a Blank/unreadable image -> Needs Review (no crash)", d5["status"] == wf.NEEDS_REVIEW, d5["review_reason"])
    i6, r6 = upload_and_run("invoice_scanned.png", dbp, root)
    d6 = db.get_document(i6, dbp)
    check("3b Scanned invoice image is OCR'd and routed (Completed or Needs Review, never failed)",
          r6["outcome"] in ("processed", "review"), f"{d6['status']}: {d6['review_reason'] or 'ok'}")

    # 4 duplicate
    n, data = sample("invoice_normal.pdf")
    dup = service.ingest(n, data, dbp, root)
    check("4 Duplicate upload is blocked and audited", (not dup.ok) and dup.duplicate_of == i1
          and any(h["action"] == "Duplicate upload blocked" for h in audit.get_history(i1, dbp)), dup.message)

    # 5 invalid extracted values
    i7, _ = upload_and_run("invoice_invalid_date.pdf", dbp, root)
    d7 = db.get_document(i7, dbp)
    check("5a Invalid date -> Needs Review, 'date' recorded invalid",
          d7["status"] == wf.NEEDS_REVIEW and "date" in d7["validation"]["invalid"], str(d7["validation"]["invalid"]))
    i8, _ = upload_and_run("invoice_invalid_amount.pdf", dbp, root)
    d8 = db.get_document(i8, dbp)
    check("5b Zero amount -> Needs Review, 'total_amount' invalid",
          d8["status"] == wf.NEEDS_REVIEW and "total_amount" in d8["validation"]["invalid"], str(d8["validation"]["invalid"]))
    v = validator.validate("Resume", {"name": "A B", "email": "not-an-email", "skills": "Python", "phone": "12"})
    check("5c Validator flags bad email and bad phone",
          "email" in v["invalid"] and "phone" in v["invalid"], str(v["invalid"]))
    check("5d Amount parsing handles formats",
          validator.parse_amount("$1,250.50") == 1250.5 and validator.parse_amount("1.250,50") == 1250.5
          and validator.parse_amount("abc") is None)

    # 6 other document type and confidence handling
    i9, _ = upload_and_run("other_memo.pdf", dbp, root)
    d9 = db.get_document(i9, dbp)
    check("6a Unsupported type 'Other' -> Needs Review", d9["status"] == wf.NEEDS_REVIEW, d9["review_reason"])
    check("6b Rule classifier stores NO confidence (never invented)", db.get_document(i1, dbp)["confidence"] is None)
    low = wf.decide("Invoice", {"valid": True, "missing": [], "invalid": {}}, confidence=0.40)
    high = wf.decide("Invoice", {"valid": True, "missing": [], "invalid": {}}, confidence=0.95)
    none = wf.decide("Invoice", {"valid": True, "missing": [], "invalid": {}}, confidence=None)
    check("6c Low confidence (0.40) -> Needs Review", low.next_status == wf.NEEDS_REVIEW, low.reason)
    check("6d High confidence (0.95) and no confidence (None) -> Approved",
          high.next_status == wf.APPROVED and none.next_status == wf.APPROVED)

    # low confidence end-to-end using a fake probabilistic model
    orig = classifier.classify
    classifier.classify = lambda text: ("Invoice", 0.35, "tfidf-model")
    try:
        _, data = sample("invoice_second.pdf")
        data += b"\n%padding-to-change-hash"
        up = service.ingest("lowconf.pdf", data, dbp, root)
        r = service.run_workflow(up.doc_id, dbp, root)
        dl = db.get_document(up.doc_id, dbp)
    finally:
        classifier.classify = orig
    check("6e End-to-end low-confidence classification -> Needs Review, confidence stored",
          r["outcome"] == "review" and dl["confidence"] == 0.35, dl["review_reason"] or r["reason"])

    # 7 database / storage failure
    bad_db = os.path.join(tmp, "no_such_dir", "x.db")
    n, data = sample("resume_normal.pdf")
    res = service.ingest("x.pdf", data + b"1", bad_db, root)
    check("7a Database failure on upload handled with a friendly message",
          (not res.ok) and "database" in res.message.lower(), res.message)
    fake_root = os.path.join(tmp, "iam_a_file")
    open(fake_root, "w").close()
    res = service.ingest("y.pdf", data + b"2", dbp, fake_root)
    check("7b Storage failure handled with a friendly message",
          (not res.ok) and "stor" in res.message.lower(), res.message)
    check("7c Failed storage left no orphan database row", db.find_by_hash(storage.sha256_bytes(data + b"2"), dbp) is None)
    r = service.run_workflow(999999, dbp, root)
    check("7d Missing document id reported as failed, not crash", r["outcome"] == "failed", r["reason"])

    # upload validation
    check("7e Unsupported extension rejected", not service.ingest("notes.txt", b"hello", dbp, root).ok)
    check("7f Empty file rejected", not service.ingest("e.pdf", b"", dbp, root).ok)
    try:
        storage.validate_upload("big.pdf", b"0" * (storage.MAX_FILE_BYTES + 1))
        too_big = False
    except storage.StorageError:
        too_big = True
    check("7g Oversized file rejected", too_big)

    # 8 invalid transitions
    blocked = []
    for old_id, target in [(i1, wf.REJECTED), (i1, wf.NEEDS_REVIEW), (i3, wf.COMPLETED), (i3, wf.NEW)]:
        try:
            wf.change_status(old_id, target, "test", db_path=dbp)
            blocked.append(False)
        except wf.InvalidTransition:
            blocked.append(True)
    check("8a Invalid transitions are blocked (Completed->Rejected, Completed->Needs Review, "
          "Needs Review->Completed, Needs Review->New)", all(blocked))
    check("8b Blocked attempt is audited and status unchanged",
          db.get_document(i1, dbp)["status"] == wf.COMPLETED
          and any(h["action"].startswith("Blocked") for h in audit.get_history(i1, dbp)))
    check("8c Transition table sanity", wf.can_transition(wf.NEW, wf.PROCESSING)
          and not wf.can_transition(wf.NEW, wf.APPROVED) and not wf.VALID_TRANSITIONS[wf.COMPLETED])
    # re-running workflow on a completed document is an invalid transition, not a crash
    r = service.run_workflow(i1, dbp, root)
    check("8d Re-running workflow on a Completed document fails safely", r["outcome"] == "failed", r["reason"])

    # 9 human review actions
    try:
        wf.reject(i3, "   ", dbp)
        empty_blocked = False
    except ValueError:
        empty_blocked = True
    check("9a Reject without a reason is refused", empty_blocked and db.get_document(i3, dbp)["status"] == wf.NEEDS_REVIEW)
    wf.reject(i3, "Total amount genuinely absent", dbp)
    d = db.get_document(i3, dbp)
    h = audit.get_history(i3, dbp)[-1]
    check("9b Reject updates status and audit (with reviewer reason)",
          d["status"] == wf.REJECTED and h["action"] == "Reviewer rejected"
          and h["old_status"] == wf.NEEDS_REVIEW and h["new_status"] == wf.REJECTED
          and "absent" in h["note"], h["note"])
    wf.approve(i4, "Email added on paper copy", dbp)
    d = db.get_document(i4, dbp)
    acts = [x["action"] for x in audit.get_history(i4, dbp)]
    check("9c Approve -> Approved -> Completed with audit", d["status"] == wf.COMPLETED
          and "Reviewer approved" in acts and acts[-1] == "Workflow completed", " | ".join(acts[-3:]))

    # 10 mixed-success batch
    tmp2, dbp2, root2 = fresh()
    ids = []
    for name in ["invoice_normal.pdf", "invoice_missing_total.pdf", "corrupt.pdf", "resume_normal.pdf"]:
        n, data = sample(name)
        ids.append(service.ingest(n, data, dbp2, root2).doc_id)
    ids.append(424242)  # does not exist
    summary = service.run_batch(ids, dbp2, root2)
    check("10a Mixed batch: 2 processed (invoice+resume), 1 review, 2 failed (corrupt file + missing id)",
          (summary["processed"], summary["review"], summary["failed"]) == (2, 1, 2),
          f"processed={summary['processed']} review={summary['review']} failed={summary['failed']}")
    check("10b One result recorded per document", len(summary["results"]) == len(ids))
    corrupt_doc = db.get_document(ids[2], dbp2)
    check("10c Corrupt file returns to 'New' with 'Processing failed' in audit and safe message",
          corrupt_doc["status"] == wf.NEW and audit.get_history(ids[2], dbp2)[-1]["action"] == "Processing failed"
          and "Traceback" not in summary["results"][2]["reason"], summary["results"][2]["reason"])
    check("10d Documents after the failure were still processed",
          db.get_document(ids[3], dbp2)["status"] == wf.COMPLETED)

    # 11 search, filters, metrics
    found = db.list_documents(search="ACME", db_path=dbp)
    check("11a Search by company", any(d["id"] == i1 for d in found), str([d["filename"] for d in found]))
    found = db.list_documents(search="INV-1001", db_path=dbp)
    check("11b Search by invoice number (also finds the scanned copy of the same invoice)",
          any(d["id"] == i1 for d in found) and all(d["fields"]["invoice_number"] == "INV-1001" for d in found),
          str([d["filename"] for d in found]))
    found = db.list_documents(search="resume", db_path=dbp)
    check("11c Search by filename/type", len(found) >= 3)
    check("11d Status filter", all(d["status"] == wf.NEEDS_REVIEW for d in db.list_documents(status=wf.NEEDS_REVIEW, db_path=dbp)))
    check("11e Latest action + timestamp present", all(d["last_action"] and d["last_action_at"]
                                                       for d in db.list_documents(db_path=dbp)))
    m = db.metrics(dbp)
    all_docs = db.list_documents(db_path=dbp)
    check("11f Metrics match the stored data",
          m["total"] == len(all_docs) and sum(m["by_status"].values()) == m["total"]
          and sum(m["by_type"].values()) == m["total"]
          and m["approved"] == sum(d["status"] == wf.APPROVED for d in all_docs)
          and m["rejected"] == sum(d["status"] == wf.REJECTED for d in all_docs),
          str({k: m[k] for k in ("total", "processed", "needs_review", "approved", "rejected", "completed", "failed")}))
    m2 = db.metrics(dbp2)
    check("11g Failed count in metrics reflects the corrupt document", m2["failed"] == 1, str(m2["failed"]))

    shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(tmp2, ignore_errors=True)
    write_report()


def write_report():
    passed = sum(1 for _, ok, _ in results if ok)
    lines = ["# Week 5 Test Results", "",
             f"**{passed} / {len(results)} checks passed**", "",
             "| # | Scenario | Result | Detail |", "|---|---|---|---|"]
    for i, (scenario, ok, detail) in enumerate(results, 1):
        lines.append(f"| {i} | {scenario} | {'PASS' if ok else 'FAIL'} | {detail.replace('|', '/')} |")
    with open("TEST_RESULTS.md", "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"\n{passed}/{len(results)} checks passed -> TEST_RESULTS.md")
    raise SystemExit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
