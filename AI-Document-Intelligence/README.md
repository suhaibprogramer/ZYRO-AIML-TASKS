# AI Document Intelligence & Workflow Platform (Week 1 MVP)

ZYROO AI/ML Internship — Task 01

A simple Streamlit app that lets a user upload a PDF or image, reads the
text, identifies whether it's an **Invoice** or **Resume**, extracts a few
key fields, and displays the result.

## Flow

```
Upload → Read Text (PyMuPDF / OCR) → Identify Type → Extract Fields → Show Result
```

## Setup

1. Create a virtual environment (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate   # on Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. (Optional, for OCR support on scanned PDFs/images) Install Tesseract OCR
   on your system:
   - **Windows:** download the installer from
     https://github.com/UB-Mannheim/tesseract/wiki
   - **macOS:** `brew install tesseract`
   - **Linux:** `sudo apt-get install tesseract-ocr`

   If Tesseract isn't installed, the app still works for normal
   (non-scanned) PDFs — only the OCR fallback is disabled.

## Run locally

```bash
streamlit run app.py
```

Then open the local URL Streamlit prints (usually http://localhost:8501).

## Testing

Test with at least 3 sample documents (put them in `samples/`):
- 2 invoices
- 1 resume

For each, check:
- Text was extracted correctly
- Document type was identified correctly
- Note any fields that were not found

## Project Structure

```
ai-document-intelligence/
├── app.py
├── requirements.txt
├── README.md
└── samples/
```

## Deployment

Deploy for free on [Streamlit Community Cloud](https://streamlit.io/cloud)
or [Hugging Face Spaces](https://huggingface.co/spaces):

1. Push this repo to GitHub.
2. Connect the repo on Streamlit Community Cloud (or create a Space on
   Hugging Face with the Streamlit SDK).
3. Point it at `app.py` as the entry file.

Note: Tesseract OCR needs to be available on the deployment environment for
the OCR fallback to work there — Streamlit Community Cloud supports this via
a `packages.txt` file containing `tesseract-ocr`.

## Notes / Limitations

- Classification is rule-based (keyword matching), not ML — good enough for
  the beginner MVP. An optional next step is a TF-IDF + Logistic Regression
  classifier once you have enough labeled samples.
- Field extraction uses simple regex/keyword rules and may miss fields on
  unusually formatted documents — that's expected and worth noting in your
  testing writeup.
