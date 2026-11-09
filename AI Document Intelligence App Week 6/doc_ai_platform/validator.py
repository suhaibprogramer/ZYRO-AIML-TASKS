"""Validation rules for extracted fields.

validate(doc_type, fields) returns:
    {
      "valid": bool,
      "missing":  [required fields that were not found],
      "invalid":  {field: reason it failed},
      "checked":  {field: "ok" | "missing" | "invalid"},
      "completeness": share of required fields that are present and valid (None if no rules),
    }
"""
import re
from datetime import date, datetime

NOT_FOUND = "Not Found"

REQUIRED_FIELDS = {
    "Invoice": ["invoice_number", "date", "company_name", "total_amount"],
    "Resume": ["name", "email", "skills"],
}

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^\+?[\d\s().\-]{7,20}$")
DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d.%m.%Y",
                "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%B %d %Y"]


def is_missing(value) -> bool:
    return value is None or str(value).strip() == "" or str(value).strip().lower() == NOT_FOUND.lower()


def valid_email(value: str) -> bool:
    return bool(EMAIL_RE.match(str(value).strip()))


def valid_phone(value: str) -> bool:
    v = str(value).strip()
    digits = re.sub(r"\D", "", v)
    return bool(PHONE_RE.match(v)) and 7 <= len(digits) <= 15


def parse_date(value):
    """Return a datetime.date for the formats we support, otherwise None."""
    v = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def valid_date(value: str) -> bool:
    return parse_date(value) is not None


def parse_amount(value):
    """Return a float for strings like '$1,250.50' / 'USD 99' / '1.250,50'; else None."""
    if value is None:
        return None
    v = re.sub(r"[^\d.,\-]", "", str(value))
    if not v or not re.search(r"\d", v):
        return None
    if "," in v and "." in v:
        # whichever separator comes last is the decimal separator
        if v.rfind(",") > v.rfind("."):
            v = v.replace(".", "").replace(",", ".")
        else:
            v = v.replace(",", "")
    elif "," in v:
        parts = v.split(",")
        v = v.replace(",", ".") if len(parts[-1]) in (1, 2) and len(parts) == 2 else v.replace(",", "")
    try:
        return float(v)
    except ValueError:
        return None


def valid_amount(value) -> bool:
    amount = parse_amount(value)
    return amount is not None and amount > 0


def _check_field(name, value):
    """Return None if valid, else a short reason string."""
    if name == "email" and not valid_email(value):
        return "not a valid email address"
    if name == "phone" and not valid_phone(value):
        return "not a valid phone number"
    if name == "date" and not valid_date(value):
        return "not a recognised date"
    if name == "total_amount" and not valid_amount(value):
        return "not a positive number"
    return None


def validate(doc_type: str, fields: dict) -> dict:
    fields = fields or {}
    required = REQUIRED_FIELDS.get(doc_type, [])
    result = {"valid": True, "missing": [], "invalid": {}, "checked": {}, "completeness": None}

    for name in required:
        value = fields.get(name)
        if is_missing(value):
            result["missing"].append(name)
            result["checked"][name] = "missing"
            continue
        why = _check_field(name, value)
        if why:
            result["invalid"][name] = why
            result["checked"][name] = "invalid"
        else:
            result["checked"][name] = "ok"

    # optional fields (phone, subtotal, tax) are validated only when they were found
    for name, value in fields.items():
        if name in required or is_missing(value):
            continue
        why = _check_field(name, value)
        if why:
            result["invalid"][name] = why
            result["checked"][name] = "invalid"
        elif name in ("phone", "subtotal", "tax"):
            result["checked"][name] = "ok"

    if required:
        ok = sum(1 for n in required if result["checked"].get(n) == "ok")
        result["completeness"] = round(ok / len(required), 2)
    result["valid"] = not result["missing"] and not result["invalid"]
    return result
