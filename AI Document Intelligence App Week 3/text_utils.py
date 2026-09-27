"""
Shared text cleaning utilities.
Used both when training the classifier and inside the Streamlit app, so
train-time and inference-time preprocessing always match.
"""

import re


def clean_text(text: str) -> str:
    """
    Clean raw text extracted from a PDF or OCR:
    - normalize line endings
    - collapse repeated blank lines
    - collapse repeated spaces/tabs
    - strip leading/trailing whitespace
    """
    if not text:
        return ""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)          # collapse repeated spaces/tabs
    text = re.sub(r"\n[ \t]*\n+", "\n\n", text)  # collapse repeated blank lines
    text = re.sub(r" *\n *", "\n", text)          # trim spaces around line breaks
    return text.strip()


def is_text_usable(text: str, min_chars: int = 15) -> bool:
    """Guard against empty or near-empty extracted text (e.g. OCR failure)."""
    return bool(text) and len(text.strip()) >= min_chars
