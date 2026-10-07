# AI Document Intelligence & Workflow Platform — Week 5

This app takes uploaded documents (invoices and resumes), reads them, checks them,
and moves them through a controlled workflow. Anything uncertain goes to a person
for review, and every step is saved in an audit history.

## The workflow

```
Upload → Process → Classify → Extract → Validate → Apply Rules → Review / Approve / Reject → Complete → Audit History
```

## Document states

| State | Meaning |
|---|---|
| New | Uploaded but not processed yet |
| Processing | Reading, classifying and extracting right now |
| Needs Review | Something is missing, invalid or uncertain |
| Approved | Accepted (by the rules or by a reviewer) |
| Rejected | A reviewer rejected it |
| Completed | Workflow finished successfully |

Allowed moves (anything else is blocked and written to the audit log):

```
New → Processing
Processing → Needs Review | Approved | New (if processing failed, so it can be retried)
Needs Review → Approved | Rejected
Approved → Completed
Rejected → Needs Review (reopen)
Completed → (final)
```

## Project files

| File | What it does |
|---|---|
| `app.py` | Streamlit pages (Upload, Review Queue, Batch, Search & Filters, Metrics) |
| `database.py` | SQLite connection, tables, search and metrics queries |
| `storage.py` | Saves files into folders by type, safe file names, size/type checks |
| `processor.py` | Reads PDFs (PyMuPDF) and images; OCR with Tesseract when there is no text |
| `classifier.py` | Invoice / Resume / Other (keyword rules; uses a trained model if `model.joblib` exists) |
| `extractor.py` | Pulls out fields with regular expressions ("Not Found" when absent) |
| `validator.py` | Checks required fields and email / phone / date / amount formats |
| `workflow.py` | States, valid transitions and the **rule engine** (no UI code) |
| `audit.py` | Writes and reads the history of every document |
| `service.py` | Connects all the steps; runs single documents and batches |
| `test_workflow.py` | 46 automated checks → `TEST_RESULTS.md` |
| `make_samples.py` | Creates the sample test documents in `sample_docs/` |

## What gets validated

* **Invoice:** invoice number, date, company name, total amount (must be a positive number).
* **Resume:** name, email, skills.
* Email, phone, date and amount formats are checked wherever those fields exist.
* The result records **exactly** which fields were missing or invalid.

## The rule engine (`workflow.py`)

`decide()` looks at the document type, the validation result, whether text was found,
and the model confidence (only if the classifier gave one). It returns a decision and a
plain-language reason. Rules live in the `RULES` list, so they can be changed or added to
without touching the Streamlit code. A document goes to **Needs Review** if:

1. no readable text was found (blank / unreadable scan),
2. the document type has no automated rules (e.g. "Other"),
3. the classifier confidence is below the threshold,
4. a required field is missing,
5. a field has an invalid format.

Otherwise it is approved automatically and completed.

## Confidence threshold

`CONFIDENCE_THRESHOLD = 0.60` in `workflow.py`. A classification below 0.60 is treated
as uncertain and sent to Needs Review. **Confidence is only used when the classifier really
provides it** (for example a scikit-learn model with `predict_proba`). The built-in keyword
rules do not produce a probability, so their confidence is stored as empty — the app never
makes up or estimates a number.

## Audit log

Each event stores: document ID, action, previous status, new status, timestamp (UTC) and a
reason / reviewer note. You can see a document's full history in **Search & Filters** (open a
document) and under each item in the **Review Queue**.

## Pages

* **Upload** – add files; optionally run the workflow straight away. Duplicates (same SHA-256 hash) are blocked.
* **Review Queue** – shows filename, type, status, review reason, extracted fields and validation results. Approve, or Reject (a reason is required). Both update the status and the audit history.
* **Batch Processing** – select several documents and run the same rules on each. Shows processed / review / failed counts and one result per document. One failed document never stops the batch.
* **Search & Filters** – filter by status; search by filename, type, company or invoice number; see the latest action and time.
* **Metrics Dashboard** – totals, processed, needs review, approved, rejected, failed, counts by type, and average processing time (measured from real timings).

## How to run

```bash
pip install -r requirements.txt
# Tesseract OCR must be installed for scanned images:
#   Ubuntu: sudo apt install tesseract-ocr     Windows: install from the UB Mannheim build
python make_samples.py        # optional: creates sample documents
streamlit run app.py
```

## How to test

```bash
python make_samples.py
python test_workflow.py       # writes TEST_RESULTS.md
```

The tests cover: normal invoice and resume, missing fields, unreadable/scanned documents,
duplicates, invalid email/date/amount, low-confidence classification, database and storage
failures, invalid transitions, review actions, mixed-success batches, search/filters and metrics.
Results are in `TEST_RESULTS.md` (46 / 46 passing).

## Notes and limits

* A document whose processing crashes (for example a corrupt PDF) goes back to **New** with a
  "Processing failed" audit entry, so it can be retried or deleted. It is counted as *failed*.
* Only documents in **New** can start the workflow; trying it on any other state is blocked and logged.
* Dates are stored in UTC.
