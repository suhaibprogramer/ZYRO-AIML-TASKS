"""
Document processing (Week 3 logic, moved out of the UI in Week 4).

Steps: Read/OCR -> Clean -> Classify -> Extract fields -> Decide status.
No Streamlit code here, so it can be tested on its own.
"""

import io
import json
import logging
import re
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image

from text_utils import clean_text, is_text_usable
from ocr_utils import preprocess_for_ocr

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "models"
NOT_FOUND = "Not Found"

try:
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

try:
    import joblib
    _vectorizer = joblib.load(MODEL_DIR / "vectorizer.joblib")
    _classifier = joblib.load(MODEL_DIR / "classifier.joblib")
    with open(MODEL_DIR / "model_info.json") as f:
        _model_info = json.load(f)
    ML_MODEL_AVAILABLE = True
except Exception:
    ML_MODEL_AVAILABLE = False
    _model_info = {}


class ProcessingError(Exception):
    """Raised with a SAFE, user-friendly message (no technical details)."""


# ----------------------------- Reading text ----------------------------- #

def _ocr_image(img: Image.Image) -> str:
    if not OCR_AVAILABLE:
        raise ProcessingError("This looks like a scanned file, but OCR is not available on this computer.")
    try:
        return pytesseract.image_to_string(preprocess_for_ocr(img))
    except Exception:
        logger.exception("OCR failed")
        raise ProcessingError("The text in this scanned file could not be read (OCR failed).")


def _read_pdf(file_bytes: bytes) -> tuple[str, str]:
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception:
        logger.exception("Could not open PDF")
        raise ProcessingError("This PDF could not be opened. It may be damaged.")

    with doc:
        text = "".join(page.get_text() for page in doc)
        if is_text_usable(text):
            return text, "PyMuPDF (text layer)"
        # No selectable text -> scanned PDF -> OCR each page
        ocr_text = ""
        for page in doc:
            pix = page.get_pixmap(dpi=200)
            ocr_text += _ocr_image(Image.open(io.BytesIO(pix.tobytes("png"))))
        return ocr_text, "OCR (scanned PDF)"


def _read_image(file_bytes: bytes) -> tuple[str, str]:
    try:
        img = Image.open(io.BytesIO(file_bytes))
        img.load()
    except Exception:
        logger.exception("Could not open image")
        raise ProcessingError("This image could not be opened. It may be damaged.")
    return _ocr_image(img), "OCR (image)"


def get_document_text(file_bytes: bytes, ext: str) -> tuple[str, str]:
    raw, method = _read_pdf(file_bytes) if ext == "pdf" else _read_image(file_bytes)
    return clean_text(raw), method


# ----------------------------- Classification ----------------------------- #

INVOICE_KEYWORDS = ["invoice", "invoice number", "total", "bill to", "amount due"]
RESUME_KEYWORDS = ["resume", "curriculum vitae", "skills", "education", "experience"]


def rule_based_classify(text: str) -> str:
    lower = text.lower()
    inv = sum(1 for k in INVOICE_KEYWORDS if k in lower)
    res = sum(1 for k in RESUME_KEYWORDS if k in lower)
    if inv == 0 and res == 0:
        return "Other"
    return "Invoice" if inv >= res else "Resume"


def classify_document(text: str) -> tuple[str, float | None, str]:
    """Returns (label, confidence or None, method). Never invents a confidence."""
    if ML_MODEL_AVAILABLE:
        vec = _vectorizer.transform([text])
        label = str(_classifier.predict(vec)[0])
        confidence = None
        if hasattr(_classifier, "predict_proba"):
            confidence = float(max(_classifier.predict_proba(vec)[0]))
        return label, confidence, f"ML model ({_model_info.get('model_name', 'unknown')})"
    return rule_based_classify(text), None, "Rule-based (no trained model found)"


# ----------------------------- Field extraction ----------------------------- #

def extract_invoice_fields(text: str) -> dict:
    fields = {k: NOT_FOUND for k in ("Invoice Number", "Date", "Company Name", "Total Amount")}

    m = re.search(r"(?:invoice|receipt)\s*(?:number|no\.?|#)\s*[:\-]?\s*([A-Za-z0-9\-]+)", text, re.I)
    if m:
        fields["Invoice Number"] = m.group(1).strip()

    m = re.search(r"\b(\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4})\b", text)
    if m:
        fields["Date"] = m.group(1)

    m = re.search(r"(?:company|vendor|billed by|paid to|from|bill from)[:\-]?\s*([A-Za-z0-9&.,\s]{3,50})", text, re.I)
    if m:
        candidate = m.group(1).strip().splitlines()[0].strip()
        if candidate:
            fields["Company Name"] = candidate

    m = re.search(r"(?:total|amount due|grand total|amount paid)[:\-]?\s*([A-Z]{0,3}\s?[\d,]+\.?\d*)", text, re.I)
    if m:
        fields["Total Amount"] = m.group(1).strip()
    return fields


def extract_resume_fields(text: str) -> dict:
    fields = {k: NOT_FOUND for k in ("Name", "Email", "Phone", "Skills")}

    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    if m:
        fields["Email"] = m.group(0)

    m = re.search(r"(\+?\d[\d\s\-()]{7,}\d)", text)
    if m:
        fields["Phone"] = m.group(1).strip()

    label_words = ("curriculum vitae", "resume", "email", "phone", "contact", "objective", "summary")
    for line in text.splitlines():
        line = line.strip()
        if not line or "@" in line or re.search(r"\d{4,}", line) or line.lower().startswith(label_words):
            continue
        fields["Name"] = line
        break

    m = re.search(r"(?:key\s+)?skills[:\-]?\s*(.+)", text, re.I)
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


# ----------------------------- Status ----------------------------- #

# If one of these is missing, the document needs a human to look at it.
IMPORTANT_FIELDS = {
    "Invoice": ["Invoice Number", "Total Amount"],
    "Resume": ["Name", "Email"],
}


def decide_status(doc_type: str, fields: dict) -> tuple[str, str]:
    """Returns (status, note). Processed or Needs Review (Failed is set elsewhere)."""
    missing = [f for f in IMPORTANT_FIELDS.get(doc_type, []) if fields.get(f, NOT_FOUND) == NOT_FOUND]
    if missing:
        return "Needs Review", "Missing: " + ", ".join(missing)
    return "Processed", ""


# ----------------------------- Main entry point ----------------------------- #

def process_document(file_bytes: bytes, ext: str) -> dict:
    """
    Runs the whole pipeline. NEVER raises: problems become status "Failed"
    with a safe message in result["error"].
    """
    result = {
        "text": "", "method": "none", "doc_type": "Other", "confidence": None,
        "classify_method": "", "fields": {}, "status": "Failed",
        "status_note": "", "error": None,
    }
    try:
        text, method = get_document_text(file_bytes, ext)
        result["method"] = method
        if not is_text_usable(text):
            raise ProcessingError("No readable text was found in this file.")

        doc_type, confidence, classify_method = classify_document(text)
        fields = extract_fields(doc_type, text)
        status, note = decide_status(doc_type, fields)
        result.update(text=text, doc_type=doc_type, confidence=confidence,
                      classify_method=classify_method, fields=fields,
                      status=status, status_note=note)
    except ProcessingError as e:
        result["error"] = str(e)
        result["status_note"] = str(e)
    except Exception:
        logger.exception("Unexpected processing error")
        result["error"] = "Something went wrong while reading this file."
        result["status_note"] = result["error"]
    return result
