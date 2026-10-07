"""Document classification.

classify(text) -> (doc_type, confidence_or_None, classifier_name)

* If a trained scikit-learn pipeline exists at MODEL_PATH (e.g. the TF-IDF +
  Logistic Regression model from Week 3) and it supports predict_proba, its
  probability is returned as the confidence.
* Otherwise the keyword-rule classifier is used. Rules do NOT produce a
  probability, so confidence is None. We never invent or estimate one.
"""
import os
import re

MODEL_PATH = "model.joblib"

INVOICE_WORDS = ["invoice", "invoice no", "invoice number", "bill to", "amount due",
                 "total due", "subtotal", "tax", "payment terms", "due date", "purchase order"]
RESUME_WORDS = ["resume", "curriculum vitae", "cv", "education", "work experience",
                "experience", "skills", "objective", "summary", "projects", "references",
                "certifications"]

_model = None
_model_loaded = False


def _load_model():
    global _model, _model_loaded
    if _model_loaded:
        return _model
    _model_loaded = True
    if os.path.exists(MODEL_PATH):
        try:
            import joblib
            _model = joblib.load(MODEL_PATH)
        except Exception:
            _model = None
    return _model


def _score(text_lower: str, words) -> int:
    return sum(1 for w in words if re.search(r"\b" + re.escape(w) + r"\b", text_lower))


def classify_rules(text: str):
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
        except Exception:
            pass  # fall back to rules
    return classify_rules(text), None, "rules"
