"""Anomaly detection: duplicate identifiers and unusual patterns.

detect(doc_id, doc_type, fields) returns a list of
    {"code": str, "severity": "high" | "medium", "message": str}
Any anomaly sends the document to manual review (see workflow.rule_anomalies).

Checks
------
arithmetic_mismatch   subtotal + tax does not equal the total (invoices)
duplicate_identifier  another document already uses this invoice number / resume email
future_date           invoice date is in the future
unusual_amount        total is far above the median of other invoices
"""
import statistics
from datetime import date

import config
import database as db
import validator


def _money(x: float) -> str:
    return f"{x:,.2f}"


def _invoice_checks(doc_id: int, fields: dict) -> list:
    found = []

    sub = validator.parse_amount(fields.get("subtotal")) if not validator.is_missing(fields.get("subtotal")) else None
    tax = validator.parse_amount(fields.get("tax")) if not validator.is_missing(fields.get("tax")) else None
    total = validator.parse_amount(fields.get("total_amount")) \
        if not validator.is_missing(fields.get("total_amount")) else None

    if sub is not None and tax is not None and total is not None \
            and round(abs(sub + tax - total), 6) > config.AMOUNT_TOLERANCE:
        found.append({"code": "arithmetic_mismatch", "severity": "high",
                      "message": f"Subtotal {_money(sub)} + tax {_money(tax)} = {_money(sub + tax)}, "
                                 f"but the invoice total is {_money(total)}"})

    number = fields.get("invoice_number")
    if not validator.is_missing(number):
        same = db.find_by_field("Invoice", "invoice_number", number, doc_id)
        if same:
            refs = ", ".join(f"#{d['id']} {d['filename']}" for d in same[:3])
            found.append({"code": "duplicate_identifier", "severity": "high",
                          "message": f"Invoice number {number} is already used by {refs}"})

    if not validator.is_missing(fields.get("date")):
        d = validator.parse_date(fields["date"])
        if d and d > date.today():
            found.append({"code": "future_date", "severity": "medium",
                          "message": f"Invoice date {d.isoformat()} is in the future"})

    if total is not None and total > 0:
        others = [validator.parse_amount(v) for v in db.field_values("Invoice", "total_amount", doc_id)]
        others = [o for o in others if o is not None and o > 0]
        if len(others) >= config.OUTLIER_MIN_DOCS:
            median = statistics.median(others)
            if total > config.OUTLIER_FACTOR * median:
                found.append({"code": "unusual_amount", "severity": "medium",
                              "message": f"Total {_money(total)} is more than {config.OUTLIER_FACTOR:g}x "
                                         f"the median invoice total ({_money(median)})"})
    return found


def _resume_checks(doc_id: int, fields: dict) -> list:
    email = fields.get("email")
    if validator.is_missing(email):
        return []
    same = db.find_by_field("Resume", "email", email, doc_id)
    if not same:
        return []
    refs = ", ".join(f"#{d['id']} {d['filename']}" for d in same[:3])
    return [{"code": "duplicate_identifier", "severity": "high",
             "message": f"Email {email} already appears on {refs}"}]


def detect(doc_id: int, doc_type: str, fields: dict) -> list:
    fields = fields or {}
    if doc_type == "Invoice":
        return _invoice_checks(doc_id, fields)
    if doc_type == "Resume":
        return _resume_checks(doc_id, fields)
    return []
