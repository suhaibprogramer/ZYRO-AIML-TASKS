"""Streamlit interface and pages. All workflow logic lives in workflow.py / service.py."""
import json

import pandas as pd
import streamlit as st

import audit
import database as db
import service
import storage
import workflow as wf

st.set_page_config(page_title="Document Workflow Platform", page_icon="📄", layout="wide")


def show_error(message: str):
    st.error(message)


@st.cache_resource
def _init():
    db.init_db()
    return True


try:
    _init()
except db.DatabaseError as exc:
    st.error(f"The database could not be opened. {exc}")
    st.stop()

PAGES = ["Upload", "Review Queue", "Batch Processing", "Search & Filters", "Metrics Dashboard"]
page = st.sidebar.radio("Page", PAGES)
st.sidebar.caption(f"Low-confidence threshold: {wf.CONFIDENCE_THRESHOLD:.2f} "
                   "(used only when the classifier provides a confidence)")


# ------------------------------------------------------------ shared widgets
def fields_table(doc):
    """Extracted fields next to their validation result."""
    checked = doc["validation"].get("checked", {})
    invalid = doc["validation"].get("invalid", {})
    rows = []
    for name, value in doc["fields"].items():
        state = checked.get(name, "not required")
        detail = invalid.get(name, "")
        rows.append({"Field": name, "Value": value, "Validation": state, "Detail": detail})
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.caption("No fields extracted for this document type.")


def history_table(doc_id):
    hist = audit.get_history(doc_id)
    if hist:
        df = pd.DataFrame(hist).rename(columns={
            "document_id": "Document ID", "action": "Action", "old_status": "Previous status",
            "new_status": "New status", "timestamp": "Timestamp (UTC)", "note": "Reason / note"})
        st.dataframe(df[["Document ID", "Action", "Previous status", "New status",
                         "Timestamp (UTC)", "Reason / note"]],
                     use_container_width=True, hide_index=True)
    else:
        st.caption("No history yet.")


def guarded(fn, *args, **kwargs):
    """Run a DB/workflow call and show friendly errors instead of tracebacks."""
    try:
        return fn(*args, **kwargs)
    except (db.DatabaseError, storage.StorageError, wf.InvalidTransition, ValueError) as exc:
        show_error(str(exc))
    except Exception:
        show_error("Something went wrong. Please try again.")
    return None


def attempt(fn, *args, **kwargs) -> bool:
    """Like guarded(), but returns True only if the action succeeded."""
    try:
        fn(*args, **kwargs)
        return True
    except (db.DatabaseError, storage.StorageError, wf.InvalidTransition, ValueError) as exc:
        show_error(str(exc))
    except Exception:
        show_error("Something went wrong. Please try again.")
    return False


# ------------------------------------------------------------------- Upload
if page == "Upload":
    st.title("Upload documents")
    st.write("Upload PDF / PNG / JPG files. Each file is stored in state **New**; "
             "tick the box to run the workflow straight away.")
    files = st.file_uploader("Choose files", type=["pdf", "png", "jpg", "jpeg"],
                             accept_multiple_files=True)
    run_now = st.checkbox("Run the workflow immediately after upload", value=True)
    if st.button("Upload", type="primary", disabled=not files):
        new_ids = []
        for f in files:
            res = service.ingest(f.name, f.getvalue())
            if res.ok:
                st.success(f"{f.name}: uploaded (ID {res.doc_id}).")
                new_ids.append(res.doc_id)
            else:
                st.warning(f"{f.name}: {res.message}")
        if run_now and new_ids:
            summary = service.run_batch(new_ids)
            st.info(f"Processed: {summary['processed']} · Needs review: {summary['review']} · "
                    f"Failed: {summary['failed']}")
            st.dataframe(pd.DataFrame(summary["results"]), use_container_width=True, hide_index=True)

# ------------------------------------------------------------ Review Queue
elif page == "Review Queue":
    st.title("Human review queue")
    queue = guarded(db.list_documents, status=wf.NEEDS_REVIEW) or []
    st.caption(f"{len(queue)} document(s) waiting for review")
    if not queue:
        st.success("Nothing to review.")
    for doc in queue:
        conf = "n/a (classifier gave none)" if doc["confidence"] is None else f"{doc['confidence']:.2f}"
        with st.expander(f"#{doc['id']} · {doc['filename']} · {doc['doc_type']}"):
            c1, c2, c3 = st.columns(3)
            c1.metric("Document type", doc["doc_type"])
            c2.metric("Status", doc["status"])
            c3.metric("Confidence", conf)
            st.warning(f"**Review reason:** {doc['review_reason'] or 'Not recorded'}")
            fields_table(doc)
            note = st.text_input("Reviewer note (required to reject)", key=f"note_{doc['id']}")
            a, r = st.columns(2)
            if a.button("✅ Approve", key=f"ap_{doc['id']}"):
                if attempt(wf.approve, doc["id"], note):
                    st.rerun()
            if r.button("❌ Reject", key=f"rj_{doc['id']}"):
                if not note.strip():
                    show_error("Please enter a short reason before rejecting.")
                elif attempt(wf.reject, doc["id"], note):
                    st.rerun()
            st.markdown("**History**")
            history_table(doc["id"])

# ------------------------------------------------------- Batch Processing
elif page == "Batch Processing":
    st.title("Batch workflow processing")
    show_all = st.checkbox("Show documents in every state (only 'New' can start the workflow)")
    docs = guarded(db.list_documents, status=None if show_all else wf.NEW) or []
    if not docs:
        st.info("No documents available. Upload some first.")
    else:
        table = pd.DataFrame([{"ID": d["id"], "Filename": d["filename"], "Status": d["status"],
                               "Type": d["doc_type"]} for d in docs])
        labels = {f"#{d['id']} · {d['filename']} ({d['status']})": d["id"] for d in docs}
        chosen = st.multiselect("Select documents", list(labels))
        st.dataframe(table, use_container_width=True, hide_index=True)
        if st.button("Run workflow on selected", type="primary", disabled=not chosen):
            summary = service.run_batch([labels[c] for c in chosen])
            c1, c2, c3 = st.columns(3)
            c1.metric("Processed", summary["processed"])
            c2.metric("Needs review", summary["review"])
            c3.metric("Failed", summary["failed"])
            st.subheader("Result for every document")
            st.dataframe(pd.DataFrame(summary["results"]).rename(columns={
                "id": "ID", "filename": "Filename", "outcome": "Outcome",
                "status": "Status", "reason": "Reason"}), use_container_width=True, hide_index=True)

# --------------------------------------------------------- Search & Filters
elif page == "Search & Filters":
    st.title("Workflow search & filters")
    c1, c2, c3 = st.columns([2, 1, 1])
    query = c1.text_input("Search filename, document type, company or invoice number")
    status = c2.selectbox("Status", ["All"] + wf.ALL_STATES)
    dtype = c3.selectbox("Document type", ["All", "Invoice", "Resume", "Other"])
    docs = guarded(db.list_documents, status=status, search=query, doc_type=dtype) or []
    st.caption(f"{len(docs)} result(s)")
    if docs:
        st.dataframe(pd.DataFrame([{
            "ID": d["id"], "Filename": d["filename"], "Type": d["doc_type"], "Status": d["status"],
            "Company": d["fields"].get("company_name", ""),
            "Invoice #": d["fields"].get("invoice_number", ""),
            "Latest action": d["last_action"], "Action time (UTC)": d["last_action_at"],
        } for d in docs]), use_container_width=True, hide_index=True)
        pick = st.selectbox("Open a document", [None] + [d["id"] for d in docs],
                            format_func=lambda i: "—" if i is None else
                            next(f"#{d['id']} · {d['filename']}" for d in docs if d["id"] == i))
        if pick:
            doc = db.get_document(pick)
            st.subheader(f"{doc['filename']} — {doc['status']}")
            if doc["review_reason"]:
                st.warning(doc["review_reason"])
            fields_table(doc)
            with st.expander("Validation details"):
                st.json(doc["validation"])
            st.markdown("**Document history (audit log)**")
            history_table(doc["id"])

# --------------------------------------------------------- Metrics Dashboard
elif page == "Metrics Dashboard":
    st.title("Workflow metrics")
    m = guarded(db.metrics)
    if m:
        cols = st.columns(4)
        cols[0].metric("Total documents", m["total"])
        cols[1].metric("Processed", m["processed"])
        cols[2].metric("Needs review", m["needs_review"])
        cols[3].metric("Failed", m["failed"])
        cols = st.columns(3)
        cols[0].metric("Approved", m["approved"])
        cols[1].metric("Rejected", m["rejected"])
        cols[2].metric("Completed", m["completed"])
        left, right = st.columns(2)
        with left:
            st.subheader("Counts by document type")
            if m["by_type"]:
                st.bar_chart(pd.Series(m["by_type"], name="Documents"))
        with right:
            st.subheader("Counts by status")
            if m["by_status"]:
                st.bar_chart(pd.Series(m["by_status"], name="Documents"))
        if m["avg_processing_ms"] is not None:
            st.caption(f"Average processing time: {m['avg_processing_ms']} ms "
                       f"(measured on {m['timed_documents']} document(s))")
        else:
            st.caption("Processing-time metrics appear once documents have been processed.")
        st.subheader("Recent workflow events")
        recent = audit.get_recent(25)
        if recent:
            st.dataframe(pd.DataFrame(recent), use_container_width=True, hide_index=True)
