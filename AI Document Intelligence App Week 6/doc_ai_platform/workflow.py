"""Workflow states, transitions and the rule-based decision engine.

This module has no UI code. The Streamlit app and the API only call into it,
so rules can change here without touching any interface.

States
------
New          uploaded but not processed
Processing   extraction, classification and checks are running
Needs Review information is missing, invalid, uncertain or suspicious
Approved     reviewer (or the rules) accepted the document
Rejected     reviewer rejected the document
Completed    workflow finished successfully
"""
from dataclasses import dataclass, field
from typing import Optional

import audit
import config
import database as db

NEW = "New"
PROCESSING = "Processing"
NEEDS_REVIEW = "Needs Review"
APPROVED = "Approved"
REJECTED = "Rejected"
COMPLETED = "Completed"

ALL_STATES = [NEW, PROCESSING, NEEDS_REVIEW, APPROVED, REJECTED, COMPLETED]

# Valid transitions: current state -> states it may move to.
VALID_TRANSITIONS = {
    NEW:          {PROCESSING},
    PROCESSING:   {NEEDS_REVIEW, APPROVED, NEW},   # NEW = processing failed or was interrupted; safe to retry
    NEEDS_REVIEW: {APPROVED, REJECTED},
    APPROVED:     {COMPLETED},
    REJECTED:     {NEEDS_REVIEW},                  # a reviewer may reopen a rejection
    COMPLETED:    set(),                           # final
}

# Document types that have validation rules. Anything else needs a human.
SUPPORTED_TYPES = {"Invoice", "Resume"}


class InvalidTransition(Exception):
    """A state change that is not allowed (the message is safe to show)."""


def can_transition(old: str, new: str) -> bool:
    return new in VALID_TRANSITIONS.get(old, set())


def change_status(doc_id: int, new_status: str, action: str, note: str = None,
                  review_reason=...) -> None:
    """Move a document to a new state (validated) and write the audit record.

    An invalid attempt changes nothing, is written to the audit log, and raises
    InvalidTransition.
    """
    doc = db.get_document(doc_id)
    if doc is None:
        raise InvalidTransition(f"Document {doc_id} does not exist.")
    old = doc["status"]
    if not can_transition(old, new_status):
        audit.log_event(doc_id, f"Blocked: {action}", old, old, f"Invalid transition {old} -> {new_status}")
        raise InvalidTransition(f"Cannot move a document from '{old}' to '{new_status}'.")
    changes = {"status": new_status}
    if review_reason is not ...:
        changes["review_reason"] = review_reason
    db.update_document(doc_id, **changes)
    audit.log_event(doc_id, action, old, new_status, note)


# ---------------------------------------------------------- decision engine
@dataclass
class Decision:
    next_status: str            # Needs Review or Approved
    action: str                 # short label for the audit log
    reason: str                 # human-readable explanation shown to the user
    triggered_rules: list = field(default_factory=list)


def decide(doc_type: str, validation: dict, confidence: Optional[float] = None,
           has_text: bool = True, anomalies: Optional[list] = None,
           threshold: Optional[float] = None) -> Decision:
    """Apply the workflow rules and return what should happen next.

    Every rule in RULES is checked; any that fires sends the document to Needs
    Review and its reason is listed. If none fires the document is approved.
    Edit RULES below to change behaviour - no UI changes needed.
    """
    ctx = {"doc_type": doc_type, "validation": validation or {}, "confidence": confidence,
           "has_text": has_text, "anomalies": anomalies or [],
           "threshold": config.CONFIDENCE_THRESHOLD if threshold is None else threshold}
    reasons, names = [], []
    for name, rule in RULES:
        message = rule(ctx)
        if message:
            names.append(name)
            reasons.append(message)
    if reasons:
        return Decision(NEEDS_REVIEW, "Sent to review", "; ".join(reasons), names)
    conf = "" if confidence is None else f"; confidence {confidence:.2f} >= {ctx['threshold']:.2f}"
    return Decision(APPROVED, "Auto-approved by rules",
                    "All required fields present and valid, no anomalies" + conf, ["all_passed"])


# Each rule takes the context and returns a reason string, or None if it does not fire.
def rule_no_text(ctx):
    if not ctx["has_text"]:
        return "No readable text could be extracted (unreadable or poor-quality scan)"


def rule_unsupported_type(ctx):
    if ctx["has_text"] and ctx["doc_type"] not in SUPPORTED_TYPES:
        return f"Document type '{ctx['doc_type']}' has no automated rules"


def rule_low_confidence(ctx):
    c = ctx["confidence"]
    if c is not None and c < ctx["threshold"]:
        return f"Low classification confidence ({c:.2f} < {ctx['threshold']:.2f})"


def rule_missing_fields(ctx):
    missing = ctx["validation"].get("missing") or []
    if ctx["doc_type"] in SUPPORTED_TYPES and missing:
        return "Missing required field(s): " + ", ".join(missing)


def rule_invalid_fields(ctx):
    invalid = ctx["validation"].get("invalid") or {}
    if ctx["doc_type"] in SUPPORTED_TYPES and invalid:
        return "Invalid field(s): " + ", ".join(f"{k} ({v})" for k, v in invalid.items())


def rule_anomalies(ctx):
    items = ctx["anomalies"]
    if items:
        return "Anomaly: " + " | ".join(a["message"] for a in items)


RULES = [
    ("no_text", rule_no_text),
    ("unsupported_type", rule_unsupported_type),
    ("low_confidence", rule_low_confidence),
    ("missing_fields", rule_missing_fields),
    ("invalid_fields", rule_invalid_fields),
    ("anomalies", rule_anomalies),
]


# ---------------------------------------------------------- review actions
def approve(doc_id: int, reviewer_note: str = "") -> None:
    change_status(doc_id, APPROVED, "Reviewer approved", reviewer_note or "Approved by reviewer",
                  review_reason=None)
    change_status(doc_id, COMPLETED, "Workflow completed", "Approved document completed")


def reject(doc_id: int, reason: str) -> None:
    if not reason or not reason.strip():
        raise ValueError("A reason is required when rejecting a document.")
    change_status(doc_id, REJECTED, "Reviewer rejected", reason.strip(), review_reason=reason.strip())
