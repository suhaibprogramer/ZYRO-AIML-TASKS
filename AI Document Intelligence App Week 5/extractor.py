"""Information extraction with regular expressions.

Missing values are stored as "Not Found" (never guessed).
"""
import re

NOT_FOUND = "Not Found"

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<!\d)(\+?\d[\d\s().\-]{7,18}\d)(?!\d)")
DATE_PATTERNS = [
    r"\b\d{4}-\d{2}-\d{2}\b",
    r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b",
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.? \d{1,2},? \d{4}\b",
    r"\b\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]* \d{4}\b",
]
SKILL_LIST = ["python", "java", "javascript", "typescript", "c++", "c#", "sql", "html", "css",
              "react", "node.js", "django", "flask", "streamlit", "pandas", "numpy",
              "scikit-learn", "tensorflow", "pytorch", "machine learning", "deep learning",
              "nlp", "data analysis", "excel", "power bi", "tableau", "git", "docker",
              "aws", "linux", "ocr", "communication", "leadership"]


def _first(patterns, text, flags=re.I):
    for p in patterns:
        m = re.search(p, text, flags)
        if m:
            return m.group(1).strip()
    return None


def extract_invoice(text: str) -> dict:
    inv_no = _first([r"invoice\s*(?:no\.?|number|#|num)\s*[:#\-]?\s*([A-Za-z0-9\-/]+)",
                     r"invoice\s*[:#]\s*([A-Za-z0-9\-/]+)"], text)
    date = _first([r"(?:invoice\s*)?date\s*[:\-]?\s*(" + "|".join(DATE_PATTERNS) + ")"], text)
    if not date:
        for p in DATE_PATTERNS:
            m = re.search(p, text, re.I)
            if m:
                date = m.group(0)
                break
    company = _first([r"(?:company|vendor|from|seller|supplier)\s*(?:name)?\s*[:\-]\s*([^\n]+)"], text)
    if not company:
        for line in text.splitlines():
            line = line.strip()
            if re.search(r"\b(?:inc|llc|ltd|limited|corp|corporation|co|company|pvt|gmbh)\b\.?", line, re.I) \
                    and len(line) < 80:
                company = line
                break
    total = _first([r"(?:grand\s+total|total\s+due|amount\s+due|total\s+amount|total)\s*[:\-]?\s*"
                    r"((?:[$€£]|USD|PKR|Rs\.?)?\s*[\d.,]+\d)"], text)
    return {"invoice_number": inv_no or NOT_FOUND, "date": date or NOT_FOUND,
            "company_name": company or NOT_FOUND, "total_amount": total or NOT_FOUND}


def extract_resume(text: str) -> dict:
    email = EMAIL_RE.search(text)
    phone = None
    for m in PHONE_RE.finditer(text):
        if len(re.sub(r"\D", "", m.group(1))) >= 7:
            phone = m.group(1).strip()
            break
    name = _first([r"(?:^|\n)\s*name\s*[:\-]\s*([A-Za-z][A-Za-z .'\-]{1,50})"], text)
    if not name:
        for line in text.splitlines():
            line = line.strip()
            if line and not re.search(r"[@\d]|resume|curriculum", line, re.I) \
                    and 2 <= len(line.split()) <= 4 and len(line) < 40:
                name = line
                break
    lower = text.lower()
    skills = [s for s in SKILL_LIST if re.search(r"(?<![a-z])" + re.escape(s) + r"(?![a-z])", lower)]
    return {"name": name or NOT_FOUND, "email": email.group(0) if email else NOT_FOUND,
            "phone": phone or NOT_FOUND, "skills": ", ".join(skills) if skills else NOT_FOUND}


def extract_fields(doc_type: str, text: str) -> dict:
    if doc_type == "Invoice":
        return extract_invoice(text)
    if doc_type == "Resume":
        return extract_resume(text)
    return {}
