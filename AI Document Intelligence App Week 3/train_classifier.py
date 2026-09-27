"""
Week 3 — Step 4/5/6: Train and compare simple classifiers, evaluate them,
and save the best one for the app to use.

Run: python train_classifier.py
Produces:
  models/vectorizer.joblib
  models/classifier.joblib
  models/model_info.json
  reports/evaluation_report.md
  reports/confusion_matrix_<model>.png
"""

import json
import os

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.svm import LinearSVC
from sklearn.naive_bayes import MultinomialNB
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score, precision_recall_fscore_support,
    classification_report, confusion_matrix
)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import joblib

from text_utils import clean_text

MODELS_DIR = "models"
REPORTS_DIR = "reports"
os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)


def rule_based_classify(text: str) -> str:
    """The Week 1/2 keyword-rule baseline, kept for comparison (Step 4)."""
    INVOICE_KEYWORDS = ["invoice", "invoice number", "total", "bill to", "amount due"]
    RESUME_KEYWORDS = ["resume", "curriculum vitae", "skills", "education", "experience"]
    lower = text.lower()
    invoice_hits = sum(1 for kw in INVOICE_KEYWORDS if kw in lower)
    resume_hits = sum(1 for kw in RESUME_KEYWORDS if kw in lower)
    if invoice_hits == 0 and resume_hits == 0:
        return "Other"
    return "Invoice" if invoice_hits >= resume_hits else "Resume"


def plot_confusion_matrix(cm, labels, title, path):
    fig, ax = plt.subplots(figsize=(5, 4))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels)
    ax.set_yticklabels(labels)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    ax.set_title(title)
    for i in range(len(labels)):
        for j in range(len(labels)):
            ax.text(j, i, cm[i, j], ha="center", va="center",
                     color="white" if cm[i, j] > cm.max() / 2 else "black")
    fig.colorbar(im)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main():
    df = pd.read_csv("dataset/dataset.csv")
    df["text_clean"] = df["text"].apply(clean_text)

    X_train, X_test, y_train, y_test = train_test_split(
        df["text_clean"], df["label"], test_size=0.25, random_state=42, stratify=df["label"]
    )

    vectorizer = TfidfVectorizer(max_features=3000, ngram_range=(1, 2))
    X_train_tfidf = vectorizer.fit_transform(X_train)
    X_test_tfidf = vectorizer.transform(X_test)

    candidates = {
        "Logistic Regression": LogisticRegression(max_iter=1000),
        "Linear SVM": LinearSVC(),
        "Naive Bayes": MultinomialNB(),
    }

    labels = sorted(df["label"].unique())
    report_lines = ["# Week 3 — Classifier Evaluation Report\n"]
    report_lines.append(f"Dataset: {len(df)} samples "
                         f"({', '.join(f'{c}: {n}' for c, n in df['label'].value_counts().items())})\n")
    report_lines.append(f"Train/test split: {len(X_train)} train / {len(X_test)} test (stratified, 75/25)\n")

    # --- Rule-based baseline ---
    baseline_preds = X_test.apply(rule_based_classify)
    baseline_acc = accuracy_score(y_test, baseline_preds)
    p, r, f1, _ = precision_recall_fscore_support(y_test, baseline_preds, average="macro", zero_division=0)
    report_lines.append("## Baseline: Rule-based keyword classifier (Week 1/2)\n")
    report_lines.append(f"- Accuracy: {baseline_acc:.3f}\n- Precision (macro): {p:.3f}\n"
                         f"- Recall (macro): {r:.3f}\n- F1 (macro): {f1:.3f}\n")
    cm = confusion_matrix(y_test, baseline_preds, labels=labels)
    plot_confusion_matrix(cm, labels, "Rule-based baseline", f"{REPORTS_DIR}/confusion_matrix_rule_based.png")

    results = {"Rule-based baseline": {"accuracy": baseline_acc, "precision": p, "recall": r, "f1": f1}}

    best_name, best_model, best_f1 = None, None, -1

    for name, model in candidates.items():
        model.fit(X_train_tfidf, y_train)
        preds = model.predict(X_test_tfidf)

        acc = accuracy_score(y_test, preds)
        p, r, f1, _ = precision_recall_fscore_support(y_test, preds, average="macro", zero_division=0)
        results[name] = {"accuracy": acc, "precision": p, "recall": r, "f1": f1}

        report_lines.append(f"## {name}\n")
        report_lines.append(f"- Accuracy: {acc:.3f}\n- Precision (macro): {p:.3f}\n"
                             f"- Recall (macro): {r:.3f}\n- F1 (macro): {f1:.3f}\n")
        report_lines.append("```\n" + classification_report(y_test, preds, zero_division=0) + "```\n")

        cm = confusion_matrix(y_test, preds, labels=labels)
        safe_name = name.lower().replace(" ", "_")
        plot_confusion_matrix(cm, labels, name, f"{REPORTS_DIR}/confusion_matrix_{safe_name}.png")

        if f1 > best_f1:
            best_name, best_model, best_f1 = name, model, f1

    report_lines.append("## Model Comparison Summary\n")
    report_lines.append("| Model | Accuracy | Precision | Recall | F1 |\n|---|---|---|---|---|\n")
    for name, m in results.items():
        report_lines.append(f"| {name} | {m['accuracy']:.3f} | {m['precision']:.3f} | "
                             f"{m['recall']:.3f} | {m['f1']:.3f} |\n")
    report_lines.append(f"\n**Selected model: {best_name}** (highest macro F1 on the test set: {best_f1:.3f})\n")
    report_lines.append(
        "\nNote: this dataset is synthetically generated for demonstration purposes. "
        "Real-world performance should be re-evaluated once genuine sample invoices/resumes "
        "are collected, as noted in the Week 3 task brief (Step 1).\n"
    )

    with open(f"{REPORTS_DIR}/evaluation_report.md", "w") as f:
        f.writelines(report_lines)

    supports_confidence = hasattr(best_model, "predict_proba")

    joblib.dump(vectorizer, f"{MODELS_DIR}/vectorizer.joblib")
    joblib.dump(best_model, f"{MODELS_DIR}/classifier.joblib")
    with open(f"{MODELS_DIR}/model_info.json", "w") as f:
        json.dump({
            "model_name": best_name,
            "supports_confidence": supports_confidence,
            "labels": labels,
            "test_f1_macro": best_f1,
        }, f, indent=2)

    print(f"Selected model: {best_name} (F1={best_f1:.3f}, confidence available: {supports_confidence})")
    print(f"Saved model + vectorizer to {MODELS_DIR}/, report to {REPORTS_DIR}/evaluation_report.md")


if __name__ == "__main__":
    main()
