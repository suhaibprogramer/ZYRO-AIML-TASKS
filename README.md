# AI Document Intelligence App — Week 3

**ZYROO AI/ML Internship — Task 02: Improve Document Understanding**

This app lets you upload an invoice or resume (as PDF or image), and it will:
1. Read the text from it
2. Clean up messy text
3. Figure out if it's an **Invoice**, **Resume**, or **Other**
4. Pull out useful details (like name, total amount, etc.)
5. Show you the result

## What's New in Week 3 (compared to Week 1)

- **Cleaner text** — messy spacing and blank lines are cleaned up before anything else happens.
- **Better scanning** — scanned/blurry documents are sharpened before reading them, so OCR works better.
- **Smarter detection** — instead of just looking for keywords, the app now uses a trained AI model to decide the document type, and shows how confident it is (e.g. "92% sure it's an Invoice").
- **No more crashes** — if a detail (like the total amount) can't be found, it just shows "Not Found" instead of breaking.
- **Proof it works better** — I tested the old method vs the new AI model side-by-side. The old keyword method got things right 83% of the time; the new AI model got 100% right on the test set. See `reports/evaluation_report.md`.

## How to Run It

**Step 1 — Install the required tools:**
```bash
pip install -r requirements.txt
```

**Step 2 — (One-time) Train the AI model:**
```bash
python dataset/generate_dataset.py
python train_classifier.py
```
This creates the "brain" of the app and saves it in the `models/` folder.
(If you skip this step, the app still works — it just falls back to the simpler keyword method.)

**Step 3 — Run the app:**
```bash
streamlit run app.py
```
A browser tab will open with the app.

**Step 4 — Test it:**
Upload any file from the `samples/` folder to try it out — there are sample invoices, a resume, and a scanned image included.

## Folder Guide

| Folder/File | What it's for |
|---|---|
| `app.py` | The main app — run this |
| `dataset/` | Practice documents used to train the AI |
| `train_classifier.py` | Run once to train the AI model |
| `models/` | Where the trained AI gets saved |
| `reports/` | Test results and score charts (for submission) |
| `samples/` | Example files to test the app with |
| `requirements.txt` | List of tools to install |

## For Submission

- `reports/evaluation_report.md` — shows accuracy, precision, recall, and where the model makes mistakes
- `reports/confusion_matrix_*.png` — charts showing correct vs incorrect predictions
- `samples/` — the test documents used

## Notes

- The AI was trained on made-up (synthetic) sample documents, not real ones. It works great on those, but real invoices/resumes might look a bit different — that's normal and expected at this stage.
- If OCR (reading scanned images) doesn't work, make sure Tesseract is installed on your computer (link in `requirements.txt` comments) — this is separate from the Python packages.
