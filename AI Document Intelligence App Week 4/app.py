"""
AI Document Intelligence & Workflow Platform
ZYROO AI/ML Internship — Week 4: Document Management Layer

Target flow:
Upload -> Validate -> Hash -> Read/OCR -> Clean -> Classify -> Extract ->
Store File -> Store Metadata -> Search/Filter -> View

All the real logic lives in storage.py, document_processor.py, database.py
and service.py — this file is just the Streamlit interface on top of them.
"""

from datetime import date

import streamlit as st

import database as db
import service
import storage

STATUS_COLOR = {"Processed": "green", "Needs Review": "orange", "Failed": "red"}

st.set_page_config(page_title="AI Document Intelligence", page_icon="📄", layout="wide")
db.init_db()


def status_badge(status: str) -> str:
    color = STATUS_COLOR.get(status, "gray")
    return f":{color}[**{status}**]"


def show_fields(doc: dict):
    if doc["document_type"] == "Invoice":
        rows = [("Invoice Number", doc["invoice_number"]), ("Date", doc["invoice_date"]),
                ("Company", doc["company"]), ("Total Amount", doc["total_amount"])]
    elif doc["document_type"] == "Resume":
        rows = [("Name", doc["person_name"]), ("Email", doc["email"]),
                ("Phone", doc["phone"]), ("Skills", doc["skills"])]
    else:
        rows = []
    for label, value in rows:
        st.write(f"**{label}:** {value if value else ':orange[Not Found]'}")


def document_detail(doc: dict, key_prefix: str):
    """Full detail view for one document: metadata, fields, status, file access."""
    st.write(f"**Original filename:** {doc['original_filename']}")
    st.write(f"**Uploaded:** {doc['upload_date']}")
    st.write(f"**Status:** {status_badge(doc['status'])}"
             + (f" — {doc['status_note']}" if doc["status_note"] else ""))
    conf = f"{doc['confidence'] * 100:.0f}%" if doc["confidence"] is not None else "n/a"
    st.write(f"**Document Type:** {doc['document_type']} | **Confidence:** {conf}")
    st.write(f"**Extraction method:** {doc['extraction_method']}")
    st.write(f"**Stored at:** `{doc['file_path']}`")

    st.markdown("**Extracted fields**")
    show_fields(doc)

    if doc["text_preview"]:
        with st.expander("Text preview"):
            st.text(doc["text_preview"])

    file_bytes = storage.read_file(doc["file_path"])
    if file_bytes:
        st.download_button("⬇️ Download original file", data=file_bytes,
                            file_name=doc["original_filename"], key=f"dl_{key_prefix}_{doc['id']}")
    else:
        st.warning("The stored file is missing on disk.")

    with st.popover("🗑️ Delete this document"):
        st.write("This permanently removes the record and the stored file.")
        if st.button("Confirm delete", key=f"del_{key_prefix}_{doc['id']}"):
            path = db.delete_document(doc["id"])
            if path:
                storage.delete_file(path)
            st.success("Deleted.")
            st.rerun()


# ----------------------------- Upload tab ----------------------------- #

def upload_tab():
    st.caption("Upload → Validate → Hash → Read/OCR → Clean → Classify → Extract → Store")

    uploaded_file = st.file_uploader("Upload a PDF or image (Invoice, Resume, or Other)",
                                      type=["pdf", "jpg", "jpeg", "png"])
    if uploaded_file is None:
        st.info(f"Supported file types: PDF, JPG, JPEG, PNG. Max size: {storage.MAX_UPLOAD_MB} MB.")
        return

    data = uploaded_file.getvalue()
    with st.spinner("Processing document..."):
        outcome = service.ingest_document(uploaded_file.name, data)

    if outcome["outcome"] == "rejected":
        st.error(outcome["message"])

    elif outcome["outcome"] == "error":
        st.error(outcome["message"])

    elif outcome["outcome"] == "duplicate":
        st.warning("This exact file has already been uploaded. Showing the existing record:")
        document_detail(outcome["document"], key_prefix="dup")

    elif outcome["outcome"] == "saved":
        doc = outcome["document"]
        if doc["status"] == "Failed":
            st.error(f"The file was saved, but could not be fully processed: {doc['status_note']}")
        elif doc["status"] == "Needs Review":
            st.warning("Saved — but some expected fields were missing. Flagged for review.")
        else:
            st.success("Document processed and saved successfully.")
        document_detail(doc, key_prefix="new")


# ----------------------------- Search / Browse tab ----------------------------- #

def search_tab():
    st.caption("Search across filename, company, invoice number, type, text preview, name, email and skills.")

    with st.form("search_form"):
        c1, c2 = st.columns([3, 1])
        query = c1.text_input("Search", placeholder="e.g. a company name, invoice number, or keyword")
        sort_choice = c2.selectbox("Sort", ["Newest first", "Oldest first"])

        c3, c4, c5, c6 = st.columns(4)
        doc_type = c3.selectbox("Document type", ["All", "Invoice", "Resume", "Other"])
        status = c4.selectbox("Status", ["All", "Processed", "Needs Review", "Failed"])
        date_from = c5.date_input("From date", value=None)
        date_to = c6.date_input("To date", value=None)

        submitted = st.form_submit_button("Search")
        cleared = st.form_submit_button("Clear filters")

    if cleared:
        st.rerun()

    results = db.search_documents(
        query=query or "",
        document_type=None if doc_type == "All" else doc_type,
        status=None if status == "All" else status,
        date_from=date_from.isoformat() if isinstance(date_from, date) else None,
        date_to=date_to.isoformat() if isinstance(date_to, date) else None,
        newest_first=(sort_choice == "Newest first"),
    )

    st.write(f"**{len(results)} document(s) found** (of {db.count_documents()} total)")

    for doc in results:
        conf = f"{doc['confidence'] * 100:.0f}%" if doc["confidence"] is not None else "n/a"
        label = (f"#{doc['id']} — {doc['original_filename']} — {doc['document_type']} "
                 f"({conf}) — {doc['status']}")
        with st.expander(label):
            document_detail(doc, key_prefix="row")


# ----------------------------- Main ----------------------------- #

def main():
    st.title("📄 AI Document Intelligence & Workflow Platform")
    st.caption("Week 4 — Document management layer: storage, SQLite, search, filters, and detail view")

    tab1, tab2 = st.tabs(["⬆️ Upload", "🔍 Search & Browse"])
    with tab1:
        upload_tab()
    with tab2:
        search_tab()


if __name__ == "__main__":
    main()
