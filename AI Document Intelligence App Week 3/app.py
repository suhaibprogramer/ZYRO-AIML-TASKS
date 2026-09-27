"""
AI Document Intelligence & Workflow Platform
ZYROO AI/ML Internship — Week 3, Task 02: Improve Document Understanding

Flow: Upload -> Read Text/OCR -> Clean Text -> Identify Type -> Extract
      Fields -> Check Missing Fields -> Show Result

What changed from the Week 1 MVP:
- Extracted text is cleaned/normalized before classification (text_utils.clean_text)
- OCR now applies grayscale/upscaling/denoising/thresholding (ocr_utils.preprocess_for_ocr)
- Classification uses a trained TF-IDF + ML model (models/) instead of only
  keyword rules; the keyword rule classifier is kept as a fallback if no
  trained model is found, and as the baseline in the evaluation report
- Missing fields show "Not Found" instead of breaking the app
- Document type is shown with a confidence score when the model supports it
"""

import io
import json
import os
import re

import streamlit as st
import fitz  # PyMuPDF
from PIL import Image

from text_utils import clean_text, is_text_usable
from ocr_utils import preprocess_for_ocr

try:
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

try:
    import joblib
    MODEL_DIR = "models"
    _vectorizer = joblib.load(os.path.join(MODEL_DIR, "vectorizer.joblib"))
    _classifier = joblib.load(os.path.join(MODEL_DIR, "classifier.joblib"))
    with open(os.path.join(MODEL_DIR, "model_info.json")) as f:
        _model_info = json.load(f)
    ML_MODEL_AVAILABLE = True
except Exception:
    ML_MODEL_AVAILABLE = False
    _model_info = {}


NOT_FOUND = "Not Found"


# ----------------------------- Text extraction ----------------------------- #

def extract_text_from_pdf(file_bytes: bytes) -> str:
    text = ""
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            text += page.get_text()
    return text.strip()


def extract_text_from_pdf_via_ocr(file_bytes: bytes) -> str:
    if not OCR_AVAILABLE:
        return ""
    text = ""
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=200)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            img = preprocess_for_ocr(img)
            text += pytesseract.image_to_string(img)
    return text.strip()


def extract_text_from_image(file_bytes: bytes) -> str:
    if not OCR_AVAILABLE:
        return ""
    img = Image.open(io.BytesIO(file_bytes))
    img = preprocess_for_ocr(img)
    return pytesseract.image_to_string(img).strip()


def get_document_text(file_bytes: bytes, file_type: str) -> tuple[str, str]:
    """Returns (cleaned_text, method_used)."""
    if file_type == "pdf":
        raw = extract_text_from_pdf(file_bytes)
        method = "PyMuPDF (text layer)"
        if not is_text_usable(raw):
            raw = extract_text_from_pdf_via_ocr(file_bytes)
            method = "OCR (scanned PDF)" if is_text_usable(raw) else "none"
    else:
        raw = extract_text_from_image(file_bytes)
        method = "OCR (image)" if is_text_usable(raw) else "none"

    return clean_text(raw), method


# ----------------------------- Classification ----------------------------- #

INVOICE_KEYWORDS = ["invoice", "invoice number", "total", "bill to", "amount due"]
RESUME_KEYWORDS = ["resume", "curriculum vitae", "skills", "education", "experience"]


def rule_based_classify(text: str) -> str:
    """Week 1/2 keyword-rule classifier — kept as a fallback and evaluation baseline."""
    lower = text.lower()
    invoice_hits = sum(1 for kw in INVOICE_KEYWORDS if kw in lower)
    resume_hits = sum(1 for kw in RESUME_KEYWORDS if kw in lower)
    if invoice_hits == 0 and resume_hits == 0:
        return "Other"
    return "Invoice" if invoice_hits >= resume_hits else "Resume"


def classify_document(text: str) -> tuple[str, float | None, str]:
    """
    Returns (label, confidence_or_None, method_used).
    Uses the trained ML model when available; falls back to keyword rules
    (with no invented confidence) otherwise.
    """
    if ML_MODEL_AVAILABLE:
        vec = _vectorizer.transform([text])
        label = _classifier.predict(vec)[0]
        confidence = None
        if hasattr(_classifier, "predict_proba"):
            proba = _classifier.predict_proba(vec)[0]
            confidence = float(max(proba))
        return label, confidence, f"ML model ({_model_info.get('model_name', 'unknown')})"

    return rule_based_classify(text), None, "Rule-based (fallback — no trained model found)"


# ----------------------------- Field extraction ----------------------------- #

def extract_invoice_fields(text: str) -> dict:
    fields = {
        "Invoice Number": NOT_FOUND,
        "Date": NOT_FOUND,
        "Company Name": NOT_FOUND,
        "Total Amount": NOT_FOUND,
    }

    m = re.search(r"(?:invoice|receipt)\s*(?:number|no\.?|#)\s*[:\-]?\s*([A-Za-z0-9\-]+)", text, re.IGNORECASE)
    if m:
        fields["Invoice Number"] = m.group(1).strip()

    m = re.search(r"\b(\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4})\b", text)
    if m:
        fields["Date"] = m.group(1)

    m = re.search(r"(?:company|vendor|billed by|paid to|from|bill from)[:\-]?\s*([A-Za-z0-9&.,\s]{3,50})",
                  text, re.IGNORECASE)
    if m:
        candidate = m.group(1).strip().splitlines()[0].strip()
        if candidate:
            fields["Company Name"] = candidate

    m = re.search(r"(?:total|amount due|grand total|amount paid)[:\-]?\s*([A-Z]{0,3}\s?[\d,]+\.?\d*)",
                  text, re.IGNORECASE)
    if m:
        fields["Total Amount"] = m.group(1).strip()

    return fields


def extract_resume_fields(text: str) -> dict:
    fields = {
        "Name": NOT_FOUND,
        "Email": NOT_FOUND,
        "Phone": NOT_FOUND,
        "Skills": NOT_FOUND,
    }

    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    if m:
        fields["Email"] = m.group(0)

    m = re.search(r"(\+?\d[\d\s\-()]{7,}\d)", text)
    if m:
        fields["Phone"] = m.group(1).strip()

    # Name heuristic: first non-empty line that isn't a label/email/phone line
    label_words = ("curriculum vitae", "resume", "email", "phone", "contact", "objective", "summary")
    for line in text.splitlines():
        line = line.strip()
        if not line or "@" in line or re.search(r"\d{4,}", line):
            continue
        if line.lower().startswith(label_words):
            continue
        fields["Name"] = line
        break

    m = re.search(r"(?:key\s+)?skills[:\-]?\s*(.+)", text, re.IGNORECASE)
    if m:
        candidate = m.group(1).strip().splitlines()[0].strip()
        if candidate:
            fields["Skills"] = candidate

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
    st.caption("Week 3 — Upload → Read Text/OCR → Clean Text → Identify Type → Extract Fields → Check Missing Fields → Show Result")

    if not OCR_AVAILABLE:
        st.warning(
            "pytesseract is not installed, so OCR for scanned PDFs/images is disabled. "
            "Text-based PDFs will still work."
        )
    if not ML_MODEL_AVAILABLE:
        st.info(
            "No trained model found in `models/` — falling back to the Week 1/2 keyword-rule "
            "classifier. Run `python train_classifier.py` after generating the dataset to enable "
            "the ML classifier and confidence scores."
        )

    uploaded_file = st.file_uploader(
        "Upload a PDF or image (Invoice or Resume)",
        type=["pdf", "jpg", "jpeg", "png"],
    )

    if uploaded_file is None:
        st.info("Upload a sample invoice, resume, or scanned document to get started.")
        return

    file_bytes = uploaded_file.read()
    file_ext = uploaded_file.name.split(".")[-1].lower()
    file_type = "pdf" if file_ext == "pdf" else "image"

    st.subheader("1. Uploaded File")
    st.write(f"**Filename:** {uploaded_file.name}")
    st.write(f"**File type:** {file_ext.upper()}")

    with st.spinner("Reading and cleaning document..."):
        text, method = get_document_text(file_bytes, file_type)

    st.subheader("2. Extracted Text (cleaned)")
    st.write(f"**Extraction method:** {method}")
    if not is_text_usable(text):
        st.error("No usable text could be extracted from this file (empty or too short).")
        return
    with st.expander("View extracted text", expanded=False):
        st.text(text)

    st.subheader("3. Document Type")
    doc_type, confidence, classify_method = classify_document(text)
    st.write(f"**Classification method:** {classify_method}")
    if confidence is not None:
        st.write(f"**Document Type:** {doc_type} | **Confidence:** {confidence * 100:.0f}%")
    else:
        st.write(f"**Document Type:** {doc_type}")

    st.subheader("4. Extracted Fields")
    fields = extract_fields(doc_type, text)
    if fields:
        for key, value in fields.items():
            if value == NOT_FOUND:
                st.write(f"**{key}:** :orange[{NOT_FOUND}]")
            else:
                st.write(f"**{key}:** {value}")
    else:
        st.write("No field extraction rules for this document type.")


if __name__ == "__main__":
    main()
