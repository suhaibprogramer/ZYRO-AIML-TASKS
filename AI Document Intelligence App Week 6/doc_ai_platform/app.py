"""Streamlit interface. All logic lives in service.py / workflow.py / rag.py / database.py;
this file only shows pages and calls those modules.

Run:  streamlit run app.py
"""
import pandas as pd
import streamlit as st

import audit
import config
import database as db
import rag
import reports
import service
import workflow as wf

st.set_page_config(page_title="Document Intelligence Platform", page_icon="📄", layout="wide")

STATUS_COLOR = {"New": "gray", "Processing": "blue", "Needs Review": "orange",
                "Approved": "green", "Rejected": "red", "Completed": "green"}
OUTCOME_LABEL = {"processed": "Completed automatically", "review": "Needs review",
                 "failed": "Failed", "skipped": "Skipped (already processed)"}


@st.cache_resource
def _startup() -> int:
    """Create tables and recover documents that were mid-processing when the app last stopped."""
    db.init_db()
    return service.recover_interrupted()


try:
    _startup()
except db.DatabaseError as exc:
    st.error(str(exc))
    st.stop()


# ------------------------------------------------------------------- helpers
def friendly(fn, *args, **kwargs):
    """Run a call and show a clear message instead of a traceback. Returns (ok, value)."""
    try:
        return True, fn(*args, **kwargs)
    except (db.DatabaseError, wf.InvalidTransition, ValueError) as exc:
        st.error(str(exc))
    except Exception:
        st.error("Something went wrong. Please try again.")
    return False, None


def status_badge(status: str) -> None:
    st.badge(status, color=STATUS_COLOR.get(status, "gray"))


def show_table(rows, columns=None) -> None:
    if not rows:
        st.caption("Nothing to show yet.")
        return
    df = pd.DataFrame(rows)
    st.dataframe(df[columns] if columns else df, width="stretch", hide_index=True)


def render_document(doc: dict, history: bool = True) -> None:
    """One consistent view of a document: status, confidence, fields, anomalies, decision, history."""
    conf = "n/a" if doc["confidence"] is None else f"{doc['confidence']:.2f}"
    comp = doc["validation"].get("completeness")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Document type", doc["doc_type"])
    with c2:
        st.caption("Status")
        status_badge(doc["status"])
    c3.metric("Classification confidence", conf,
              help="Shown only when a trained model gives a probability. The keyword rules give no score, "
                   "so none is shown (it is never invented).")
    c4.metric("Required fields found", "n/a" if comp is None else f"{comp:.0%}")
    c5.metric("Text source", {"pdf-text": "PDF text", "ocr": "OCR"}.get(doc.get("text_method"), "n/a"))

    if doc["review_reason"]:
        st.warning(f"**Why this needs attention:** {doc['review_reason']}")
    for a in doc["anomalies"]:
        st.error(f"**Anomaly ({a['severity']}):** {a['message']}")

    checked, invalid = doc["validation"].get("checked", {}), doc["validation"].get("invalid", {})
    show_table([{"Field": k, "Value": v, "Validation": checked.get(k, "not required"),
                 "Detail": invalid.get(k, "")} for k, v in doc["fields"].items()])

    with st.expander("Extracted text"):
        st.text(doc.get("extracted_text") or "(no text extracted)")
    if doc["timings"]:
        with st.expander("Processing time per stage"):
            show_table([{"Stage": k.replace("_", " "), "Milliseconds": v} for k, v in doc["timings"].items()])
    if history:
        with st.expander("Workflow history (audit log)", expanded=False):
            show_table([{"Action": h["action"], "Previous status": h["old_status"], "New status": h["new_status"],
                         "Timestamp (UTC)": h["timestamp"], "Reason / note": h["note"]}
                        for h in audit.get_history(doc["id"])])


# ------------------------------------------------------------------ sidebar
PAGES = ["Upload", "Review Queue", "Batch Processing", "Search & Filters", "AI Assistant", "Dashboard"]
st.sidebar.title("📄 Document Intelligence")
page = st.sidebar.radio("Navigate", PAGES, label_visibility="collapsed")
ok, m_side = friendly(db.metrics)
if ok:
    st.sidebar.caption(f"{m_side['total']} documents · {m_side['needs_review']} awaiting review")

# -------------------------------------------------------------------- Upload
if page == "Upload":
    st.title("Upload documents")
    st.write("Supported: PDF, PNG and JPG invoices and resumes (scans are read with OCR). "
             f"Maximum size {config.MAX_FILE_BYTES // (1024 * 1024)} MB per file.")
    files = st.file_uploader("Choose files", type=["pdf", "png", "jpg", "jpeg"], accept_multiple_files=True)
    run_now = st.checkbox("Run the workflow immediately after upload", value=True)
    if st.button("Upload", type="primary", disabled=not files):
        rows, processed_ids = [], []
        for f in files:
            res = service.upload_and_process(f.name, f.getvalue(), run_now)
            up, w = res["upload"], res["workflow"]
            if not up.ok:
                rows.append({"File": f.name, "Result": "Not accepted", "Status": "—", "Details": up.message})
            elif w is None:
                rows.append({"File": f.name, "Result": "Uploaded", "Status": wf.NEW, "Details": "Ready to process"})
            else:
                rows.append({"File": f.name, "Result": OUTCOME_LABEL[w["outcome"]], "Status": w["status"],
                             "Details": w["reason"]})
                processed_ids.append(up.doc_id)
        show_table(rows)
        for doc_id in processed_ids:
            ok, doc = friendly(db.get_document, doc_id)
            if ok and doc:
                with st.expander(f"#{doc['id']} · {doc['filename']} — {doc['status']}", expanded=len(processed_ids) == 1):
                    render_document(doc)

# -------------------------------------------------------------- Review Queue
elif page == "Review Queue":
    st.title("Review queue")
    ok, queue = friendly(db.list_documents, status=wf.NEEDS_REVIEW)
    queue = queue or []
    st.caption(f"{len(queue)} document(s) waiting for a decision")
    if not queue:
        st.success("Nothing to review.")
    for doc in queue:
        with st.expander(f"#{doc['id']} · {doc['filename']} · {doc['doc_type']}"):
            render_document(doc)
            note = st.text_input("Reviewer note (required to reject)", key=f"note_{doc['id']}")
            a, r = st.columns(2)
            if a.button("Approve", key=f"ap_{doc['id']}", type="primary"):
                if friendly(wf.approve, doc["id"], note)[0]:
                    st.rerun()
            if r.button("Reject", key=f"rj_{doc['id']}"):
                if not note.strip():
                    st.error("Please enter a reason before rejecting.")
                elif friendly(wf.reject, doc["id"], note)[0]:
                    st.rerun()

# ---------------------------------------------------------- Batch Processing
elif page == "Batch Processing":
    st.title("Batch processing")
    ok, new_docs = friendly(db.list_documents, status=wf.NEW)
    new_docs = new_docs or []
    if not new_docs:
        st.info("No documents are waiting. Upload documents without running the workflow, or retry failed ones here.")
    else:
        labels = {f"#{d['id']} · {d['filename']}": d["id"] for d in new_docs}
        select_all = st.checkbox("Select all waiting documents")
        chosen = st.multiselect("Documents to process", list(labels), default=list(labels) if select_all else [])
        if st.button("Run workflow", type="primary", disabled=not chosen):
            with st.spinner("Processing..."):
                summary = service.run_batch([labels[c] for c in chosen])
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Completed automatically", summary["processed"])
            c2.metric("Needs review", summary["review"])
            c3.metric("Failed", summary["failed"])
            c4.metric("Skipped", summary["skipped"])
            st.caption(f"Finished in {summary['seconds']} s. One failed document never stops the others.")
            show_table([{"ID": r["id"], "File": r["filename"], "Result": OUTCOME_LABEL[r["outcome"]],
                         "Status": r["status"], "Details": r["reason"]} for r in summary["results"]])

# -------------------------------------------------------------- Search & Filters
elif page == "Search & Filters":
    st.title("Search & filters")
    c1, c2, c3, c4 = st.columns([3, 1.3, 1.3, 1.3])
    query = c1.text_input("Search", placeholder="filename, company, invoice number, name or email")
    status = c2.selectbox("Status", ["All"] + wf.ALL_STATES)
    dtype = c3.selectbox("Type", ["All", "Invoice", "Resume", "Other"])
    sort = c4.selectbox("Sort by", ["Newest", "Oldest", "Filename", "Status"])
    ok, docs = friendly(db.list_documents, status=status, search=query, doc_type=dtype)
    docs = docs or []
    docs = {"Newest": docs, "Oldest": docs[::-1],
            "Filename": sorted(docs, key=lambda d: d["filename"].lower()),
            "Status": sorted(docs, key=lambda d: d["status"])}[sort]
    st.caption(f"{len(docs)} result(s)")
    show_table([{"ID": d["id"], "File": d["filename"], "Type": d["doc_type"], "Status": d["status"],
                 "Company / name": d["fields"].get("company_name") or d["fields"].get("name", ""),
                 "Invoice #": d["fields"].get("invoice_number", ""),
                 "Anomalies": len(d["anomalies"]), "Latest action": d["last_action"],
                 "Action time (UTC)": d["last_action_at"]} for d in docs])
    if docs:
        pick = st.selectbox("Open a document", [d["id"] for d in docs], index=None, placeholder="Choose a document",
                            format_func=lambda i: next(f"#{d['id']} · {d['filename']}" for d in docs if d["id"] == i))
        if pick:
            ok, doc = friendly(db.get_document, pick)
            if ok and doc:
                st.subheader(doc["filename"])
                render_document(doc)
    ok, csv_text = friendly(reports.documents_csv)
    if ok:
        st.download_button("Download all documents (CSV)", csv_text, "documents.csv", "text/csv")

# --------------------------------------------------------------- AI Assistant
elif page == "AI Assistant":
    st.title("AI assistant")
    st.write("Ask a question about your documents. Answers come only from the stored documents and show the "
             "source. If the documents do not contain the answer, the assistant says so.")
    with st.form("ask_form", clear_on_submit=False):
        question = st.text_input("Your question", placeholder="e.g. What is the total amount on invoice INV-1001?")
        asked = st.form_submit_button("Ask", type="primary")
    if asked:
        ok, res = friendly(rag.ask, question)
        if ok:
            st.session_state["last_answer"] = (question, res)
    if "last_answer" in st.session_state:
        q, res = st.session_state["last_answer"]
        st.markdown(f"**Question:** {q}")
        if res["grounded"]:
            st.success(res["answer"])
            show_table([{"Document": s["filename"], "ID": s["document_id"], "Document status": s["status"],
                         "Chunk": s["chunk_index"], "Match score": s["score"], "Source text": s["snippet"]}
                        for s in res["sources"]])
        else:
            st.warning(res["answer"])
        if res["grounded"]:
            st.caption(f"Best match {res['top_score']:.2f} · question terms found in documents "
                       f"{res['coverage']:.0%} · {res['reason']}")
        else:
            st.caption(f"Why: {res['reason']}")
    ok, missed = friendly(db.recent_questions, 10, True)
    if ok and missed:
        with st.expander("Questions the documents could not answer"):
            show_table([{"Asked at (UTC)": r["asked_at"], "Question": r["question"],
                         "Best match": r["top_score"]} for r in missed])

# ------------------------------------------------------------------ Dashboard
elif page == "Dashboard":
    st.title("Dashboard")
    ok, m = friendly(db.metrics)
    if ok:
        r1 = st.columns(6)
        for col, (label, key) in zip(r1, [("Total documents", "total"), ("Processed", "processed"),
                                          ("Needs review", "needs_review"), ("Approved", "approved"),
                                          ("Rejected", "rejected"), ("Completed", "completed")]):
            col.metric(label, m[key])
        r2 = st.columns(6)
        for col, (label, val) in zip(r2, [("Validation passed", m["validation_passed"]),
                                          ("Validation failed", m["validation_failed"]),
                                          ("With anomalies", m["documents_with_anomalies"]),
                                          ("Failed processing", m["failed"]),
                                          ("Duplicates blocked", m["duplicates_blocked"]),
                                          ("Rejected uploads", m["rejected_uploads"])]):
            col.metric(label, val)

        left, right = st.columns(2)
        with left:
            st.subheader("Documents by type")
            if m["by_type"]:
                st.bar_chart(pd.Series(m["by_type"], name="Documents"))
        with right:
            st.subheader("Documents by workflow status")
            if m["by_status"]:
                st.bar_chart(pd.Series(m["by_status"], name="Documents"))

        left, right = st.columns(2)
        with left:
            st.subheader("Anomalies by kind")
            if m["anomalies_by_code"]:
                st.bar_chart(pd.Series(m["anomalies_by_code"], name="Documents"))
            else:
                st.caption("No anomalies recorded.")
        with right:
            st.subheader("Processing time")
            if m["avg_processing_ms"] is not None:
                st.caption(f"Average {m['avg_processing_ms']} ms per document "
                           f"(measured on {m['timed_documents']} documents). "
                           f"Slowest stage: {m['slowest_stage'].replace('_', ' ')}.")
                show_table([{"Stage": k.replace("_", " "), "Average ms": v}
                            for k, v in sorted(m["stage_avg_ms"].items(), key=lambda kv: -kv[1])])
            else:
                st.caption("Timings appear once documents have been processed.")

        st.subheader("AI assistant usage")
        c1, c2 = st.columns(2)
        c1.metric("Questions asked", m["questions_asked"])
        c2.metric("Not enough information", m["questions_unanswered"])

        st.subheader("Recent workflow activity")
        show_table([{"Time (UTC)": r["timestamp"], "Document": f"#{r['document_id']} {r['filename'] or ''}",
                     "Action": r["action"], "From": r["old_status"], "To": r["new_status"], "Note": r["note"]}
                    for r in audit.get_recent(25)])
        rej = db.recent_rejections(10)
        if rej:
            with st.expander("Recently rejected uploads (never stored)"):
                show_table([{"Time (UTC)": r["rejected_at"], "File": r["filename"], "Reason": r["reason"]} for r in rej])
        ok, csv_text = friendly(reports.documents_csv)
        if ok:
            st.download_button("Download full report (CSV)", csv_text, "document_report.csv", "text/csv")
