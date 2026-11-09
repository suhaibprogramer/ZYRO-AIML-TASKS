"""Document classification.

classify(text) -> (doc_type, confidence_or_None, classifier_name)

* If a trained scikit-learn pipeline exists at config.MODEL_PATH (for example the
  TF-IDF + Logistic Regression model from Week 3) and it supports predict_proba,
  its probability is returned as the confidence.
* Otherwise the keyword-rule classifier is used. Rules do not produce a
  probability, so the confidence is None. We never invent or estimate one.
"""
import logging
import os
import re

import config

log = logging.getLogger(__name__)

INVOICE_WORDS = ["invoice", "invoice no", "invoice number", "bill to", "amount due",
                 "total due", "subtotal", "tax", "payment terms", "due date", "purchase order"]
RESUME_WORDS = ["resume", "curriculum vitae", "cv", "education", "work experience",
                "experience", "skills", "objective", "summary", "projects", "references",
                "certifications"]

_state = {"model": None, "loaded_path": None}


def reset_model_cache() -> None:
    """Forget the loaded model (used after config.MODEL_PATH changes)."""
    _state["model"], _state["loaded_path"] = None, None


def _load_model():
    """Load the optional trained model once per path (reused across documents)."""
    path = config.MODEL_PATH
    if _state["loaded_path"] == path:
        return _state["model"]
    _state["loaded_path"], _state["model"] = path, None
    if path and os.path.exists(path):
        try:
            import joblib
            _state["model"] = joblib.load(path)
        except Exception as exc:  # a broken model file must not stop the app
            log.warning("Could not load classifier model %s: %s", path, exc)
    return _state["model"]


def _score(text_lower: str, words) -> int:
    return sum(1 for w in words if re.search(r"\b" + re.escape(w) + r"\b", text_lower))


def classify_rules(text: str) -> str:
    t = (text or "").lower()
    inv, res = _score(t, INVOICE_WORDS), _score(t, RESUME_WORDS)
    if inv >= 2 and inv > res:
        return "Invoice"
    if res >= 2 and res > inv:
        return "Resume"
    return "Other"


def classify(text: str):
    """Return (doc_type, confidence or None, classifier name)."""
    if not text or not text.strip():
        return "Other", None, "rules"
    model = _load_model()
    if model is not None and hasattr(model, "predict_proba"):
        try:
            probs = model.predict_proba([text])[0]
            idx = int(probs.argmax())
            label = str(model.classes_[idx])
            label = {"invoice": "Invoice", "resume": "Resume"}.get(label.lower(), label)
            return label, float(probs[idx]), "tfidf-model"
        except Exception as exc:
            log.warning("Model prediction failed, using rules: %s", exc)
    return classify_rules(text), None, "rules"
