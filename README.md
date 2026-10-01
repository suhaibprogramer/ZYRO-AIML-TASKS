# AI Document Intelligence App — Week 4

**ZYROO AI/ML Internship — Document Management Layer**

This app now does more than just read one document at a time — it keeps
track of every document you upload, saves the file safely, stores its
details in a database, and lets you search, filter, and look back at
anything you've uploaded before.

## What's New in Week 4

- **Organized storage** — uploaded files are automatically sorted into
  `storage/invoices/`, `storage/resumes/`, or `storage/other/`, and saved
  under a safe random filename (so two files with the same name never
  overwrite each other).
- **A real database** — every upload's details (type, company, invoice
  number, total, name, email, etc.) are saved in a SQLite database
  (`data/documents.db`) so nothing is lost when you close the app.
- **Duplicate detection** — if you upload the exact same file twice, the
  app recognizes it (using a fingerprint of the file) and shows you the
  existing record instead of saving it again.
- **Search & filters** — search by filename, company, invoice number,
  name, email, skills, or any text in the document. Filter by document
  type, status, or date, and sort newest/oldest first.
- **Document detail view** — click any result to see everything about it:
  its extracted fields, status, where it's stored, and a download button.
- **Safer error handling** — unsupported files, broken files, oversized
  files, and even a broken database are all handled with a clear message
  instead of crashing the app.

## How to Run It

**Step 1 — Install the required tools:**
```bash
pip install -r requirements.txt
```

**Step 2 — (One-time) Train the AI model**, if you haven't already:
```bash
python dataset/generate_dataset.py
python train_classifier.py
```

**Step 3 — Run the app:**
```bash
streamlit run app.py
```

**Step 4 — Use it:**
- Go to the **Upload** tab to add a document.
- Go to the **Search & Browse** tab to look up anything you've already
  uploaded, filter the list, or open a document's full details.

The database and stored files live in `data/` and `storage/` — they stay
there even after you close and reopen the app.

## How Duplicate Detection Works

Every file gets a unique "fingerprint" (a SHA-256 hash) calculated from its
content, not its name. Before saving a new upload, the app checks whether
that exact fingerprint already exists. If it does, nothing new is saved —
you're just shown the document that's already there. Renaming a file and
re-uploading it will still be caught, since the fingerprint is based on
content, not the filename.

## Supported Files

- PDF, JPG, JPEG, PNG
- Max size: 10 MB
- The app also checks that the file's actual content matches its extension
  (so a renamed `.txt` file pretending to be a `.png` gets rejected).

## Testing

Run the full automated test suite (uses a temporary database so your real
data is untouched):
```bash
python test_repository.py
```
This tests 12+ sample documents (invoices, resumes, other, scanned images,
duplicates, and documents with missing fields), plus error cases (corrupt
files, oversized files, a broken database). Results are written to
`reports/week4_test_results.md`.

## Folder Guide

| Folder/File | What it's for |
|---|---|
| `app.py` | The main app — run this |
| `service.py` | Runs the full upload pipeline (validate → hash → process → save) |
| `database.py` | All the database code (save, search, update, delete) |
| `storage.py` | Saves files safely and checks file type/size |
| `document_processor.py` | Reads, cleans, classifies, and extracts fields from a document |
| `data/` | The SQLite database file lives here |
| `storage/` | Uploaded files live here, sorted by type |
| `dataset/`, `models/` | The AI model and the data used to train it |
| `reports/` | Test results and model evaluation charts |
| `samples/week4/` | Sample documents used for testing |
| `test_repository.py` | Automated tests for everything above |

## Notes

- The AI model is trained on made-up (synthetic) sample documents — see
  `reports/evaluation_report.md` for how well it performs.
- If a file can't be processed (e.g. a damaged PDF), it's still saved with
  a status of **Failed** so you have a record of it — it just won't have
  extracted fields.
- A status of **Needs Review** means the document was read fine, but an
  important field (like the invoice number or email) couldn't be found.
