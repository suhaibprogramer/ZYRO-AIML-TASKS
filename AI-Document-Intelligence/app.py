"""
AI Document Intelligence & Workflow Platform — Week 1 MVP
ZYROO AI/ML Internship — Task 01

Flow: Upload -> Read Text (PDF / OCR) -> Identify Type -> Extract Fields -> Show Result
"""

import io
import re

import streamlit as st
import fitz  # PyMuPDF
from PIL import Image

try:
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False


# ----------------------------- Text extraction ----------------------------- #

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract selectable text from a normal (non-scanned) PDF using PyMuPDF."""
    text = ""
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            text += page.get_text()
    return text.strip()


def extract_text_from_pdf_via_ocr(file_bytes: bytes) -> str:
    """Fallback for scanned PDFs with no selectable text: rasterize pages and OCR them."""
    if not OCR_AVAILABLE:
        return ""
    text = ""
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=200)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            text += pytesseract.image_to_string(img)
    return text.strip()


def extract_text_from_image(file_bytes: bytes) -> str:
    """OCR a JPG/PNG image."""
    if not OCR_AVAILABLE:
        return ""
    img = Image.open(io.BytesIO(file_bytes))
    return pytesseract.image_to_string(img).strip()


def get_document_text(file_bytes: bytes, file_type: str) -> tuple[str, str]:
    """
    Returns (extracted_text, method_used).
    For PDFs: try normal text extraction first, fall back to OCR if empty.
    For images: OCR directly.
    """
    if file_type == "pdf":
        text = extract_text_from_pdf(file_bytes)
        if text:
            return text, "PyMuPDF (text layer)"
        text = extract_text_from_pdf_via_ocr(file_bytes)
        return text, "OCR (scanned PDF)" if text else "none"
    else:  # jpg / jpeg / png
        text = extract_text_from_image(file_bytes)
        return text, "OCR (image)" if text else "none"


# ----------------------------- Classification ----------------------------- #

INVOICE_KEYWORDS = ["invoice", "invoice number", "total", "bill to", "amount due"]
RESUME_KEYWORDS = ["resume", "curriculum vitae", "skills", "education", "experience"]


def classify_document(text: str) -> str:
    """Very simple keyword-based rule classifier."""
    lower = text.lower()
    invoice_hits = sum(1 for kw in INVOICE_KEYWORDS if kw in lower)
    resume_hits = sum(1 for kw in RESUME_KEYWORDS if kw in lower)

    if invoice_hits == 0 and resume_hits == 0:
        return "Other"
    return "Invoice" if invoice_hits >= resume_hits else "Resume"


# ----------------------------- Field extraction ----------------------------- #

def extract_invoice_fields(text: str) -> dict:
    fields = {
        "Invoice Number": None,
        "Date": None,
        "Company Name": None,
        "Total Amount": None,
    }

    m = re.search(r"invoice\s*(?:no|number|#)?[:\-]?\s*([A-Za-z0-9\-]+)", text, re.IGNORECASE)
    if m:
        fields["Invoice Number"] = m.group(1).strip()

    m = re.search(r"\b(\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4})\b", text)
    if m:
        fields["Date"] = m.group(1)

    m = re.search(r"(?:company|from|bill from)[:\-]?\s*([A-Za-z0-9&.,\s]{3,50})", text, re.IGNORECASE)
    if m:
        fields["Company Name"] = m.group(1).strip().splitlines()[0]

    m = re.search(r"(?:total|amount due|grand total)[:\-]?\s*([A-Z]{0,3}\s?[\d,]+\.?\d*)", text, re.IGNORECASE)
    if m:
        fields["Total Amount"] = m.group(1).strip()

    return fields


def extract_resume_fields(text: str) -> dict:
    fields = {
        "Name": None,
        "Email": None,
        "Phone": None,
        "Skills": None,
    }

    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    if m:
        fields["Email"] = m.group(0)

    m = re.search(r"(\+?\d[\d\s\-()]{7,}\d)", text)
    if m:
        fields["Phone"] = m.group(1).strip()

    # Name heuristic: first non-empty line that isn't the email/phone line
    for line in text.splitlines():
        line = line.strip()
        if line and "@" not in line and not re.search(r"\d{4,}", line):
            fields["Name"] = line
            break

    m = re.search(r"skills[:\-]?\s*(.+)", text, re.IGNORECASE)
    if m:
        fields["Skills"] = m.group(1).strip().splitlines()[0]

    return fields


def extract_fields(doc_type: str, text: str) -> dict:
    if doc_type == "Invoice":
        return extract_invoice_fields(text)
    if doc_type == "Resume":
        return extract_resume_fields(text)
    return {}


# ----------------------------- Streamlit UI ----------------------------- #

def main():
    st.set_page_config(page_title="AI Document Intelligence", page_icon="📄", layout="centered")
    st.title("📄 AI Document Intelligence & Workflow Platform")
    st.caption("Week 1 MVP — Upload → Read Text → Identify Type → Extract Fields → Show Result")

    if not OCR_AVAILABLE:
        st.warning(
            "pytesseract is not installed, so OCR fallback for scanned PDFs/images is disabled. "
            "Text-based PDFs will still work."
        )

    uploaded_file = st.file_uploader(
        "Upload a PDF or image (Invoice or Resume)",
        type=["pdf", "jpg", "jpeg", "png"],
    )

    if uploaded_file is None:
        st.info("Upload a sample invoice or resume to get started.")
        return

    file_bytes = uploaded_file.read()
    file_ext = uploaded_file.name.split(".")[-1].lower()
    file_type = "pdf" if file_ext == "pdf" else "image"

    st.subheader("1. Uploaded File")
    st.write(f"**Filename:** {uploaded_file.name}")
    st.write(f"**File type:** {file_ext.upper()}")

    with st.spinner("Reading document..."):
        text, method = get_document_text(file_bytes, file_type)

    st.subheader("2. Extracted Text")
    st.write(f"**Extraction method:** {method}")
    if text:
        with st.expander("View extracted text", expanded=False):
            st.text(text)
    else:
        st.error("No text could be extracted from this file.")
        return

    st.subheader("3. Document Type")
    doc_type = classify_document(text)
    st.write(f"**Detected type:** {doc_type}")

    st.subheader("4. Extracted Fields")
    fields = extract_fields(doc_type, text)
    if fields:
        for key, value in fields.items():
            st.write(f"**{key}:** {value if value else '_not found_'}")
    else:
        st.write("No field extraction rules for this document type.")


if __name__ == "__main__":
    main()
