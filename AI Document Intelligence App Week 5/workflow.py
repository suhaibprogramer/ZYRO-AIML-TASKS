"""Workflow states, transitions and the rule-based decision engine.

This module has NO Streamlit code. The UI only calls into it, so rules can be
changed here without touching the interface.

States
------
New          uploaded but not processed
Processing   extraction and classification are running
Needs Review information is missing, invalid or uncertain
Approved     reviewer (or the rules) accepted the document
Rejected     reviewer rejected the document
Completed    workflow finished successfully
"""
from dataclasses import dataclass, field
from typing import Optional

import audit
import database as db

# ----------------------------------------------------------------- states
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
    PROCESSING:   {NEEDS_REVIEW, APPROVED, NEW},   # NEW = processing failed, safe to retry
    NEEDS_REVIEW: {APPROVED, REJECTED},
    APPROVED:     {COMPLETED},
    REJECTED:     {NEEDS_REVIEW},                  # reviewer may reopen a rejection
    COMPLETED:    set(),                           # final
}

# ------------------------------------------------------ documented threshold
# A classification whose model confidence is BELOW this value is "uncertain"
# and goes to Needs Review. The threshold is only used when the classifier
# actually returns a confidence; we never invent one.
CONFIDENCE_THRESHOLD = 0.60

# Document types that have validation rules. Anything else needs a human.
SUPPORTED_TYPES = {"Invoice", "Resume"}


class InvalidTransition(Exception):
    """Raised when someone tries a state change that is not allowed."""


def can_transition(old: str, new: str) -> bool:
    return new in VALID_TRANSITIONS.get(old, set())


def change_status(doc_id: int, new_status: str, action: str, note: str = None,
                  review_reason: Optional[str] = ..., db_path=None) -> None:
    """Move a document to a new state (validated) and write the audit record.

    Raises InvalidTransition (and logs nothing in the document row) if the
    change is not permitted. The invalid attempt itself is audited.
    """
    doc = db.get_document(doc_id, db_path)
    if doc is None:
        raise InvalidTransition(f"Document {doc_id} does not exist.")
    old = doc["status"]
    if not can_transition(old, new_status):
        audit.log_event(doc_id, f"Blocked: {action}", old, old,
                        f"Invalid transition {old} -> {new_status}", db_path)
        raise InvalidTransition(f"Cannot move a document from '{old}' to '{new_status}'.")
    changes = {"status": new_status}
    if review_reason is not ...:
        changes["review_reason"] = review_reason
    db.update_document(doc_id, db_path, **changes)
    audit.log_event(doc_id, action, old, new_status, note, db_path)


# ---------------------------------------------------------- decision engine
@dataclass
class Decision:
    next_status: str            # Needs Review or Approved
    action: str                 # short label for the audit log
    reason: str                 # human-readable explanation
    triggered_rules: list = field(default_factory=list)


def decide(doc_type: str, validation: dict, confidence: Optional[float] = None,
           has_text: bool = True, threshold: float = CONFIDENCE_THRESHOLD) -> Decision:
    """Apply the workflow rules and return what should happen next.

    Rules are checked in priority order; the first that fires sends the
    document to Needs Review. If none fire it is approved automatically.
    Edit RULES below to change behaviour - no UI changes needed.
    """
    ctx = {"doc_type": doc_type, "validation": validation or {}, "confidence": confidence,
           "has_text": has_text, "threshold": threshold}
    reasons, names = [], []
    for name, rule in RULES:
        message = rule(ctx)
        if message:
            names.append(name)
            reasons.append(message)
    if reasons:
        return Decision(NEEDS_REVIEW, "Sent to review", "; ".join(reasons), names)
    return Decision(APPROVED, "Auto-approved by rules",
                    "All required fields present and valid"
                    + ("" if confidence is None else f"; confidence {confidence:.2f} >= {threshold:.2f}"),
                    ["all_passed"])


# --- individual rules: each takes ctx and returns a reason string or None ---
def rule_no_text(ctx):
    if not ctx["has_text"]:
        return "No readable text could be extracted (unreadable or scanned document)"


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


RULES = [
    ("no_text", rule_no_text),
    ("unsupported_type", rule_unsupported_type),
    ("low_confidence", rule_low_confidence),
    ("missing_fields", rule_missing_fields),
    ("invalid_fields", rule_invalid_fields),
]


# ---------------------------------------------------------- review actions
def approve(doc_id: int, reviewer_note: str = "", db_path=None) -> None:
    change_status(doc_id, APPROVED, "Reviewer approved", reviewer_note or "Approved by reviewer",
                  review_reason=None, db_path=db_path)
    # an approved document completes the workflow
    change_status(doc_id, COMPLETED, "Workflow completed", "Approved document completed",
                  db_path=db_path)


def reject(doc_id: int, reason: str, db_path=None) -> None:
    if not reason or not reason.strip():
        raise ValueError("A reason is required when rejecting a document.")
    change_status(doc_id, REJECTED, "Reviewer rejected", reason.strip(),
                  review_reason=reason.strip(), db_path=db_path)
