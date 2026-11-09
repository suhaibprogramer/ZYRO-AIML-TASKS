# Deployment

## Option 1 – Run directly (tested)

```bash
sudo apt install tesseract-ocr
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # edit if needed
streamlit run app.py            # UI on :8501
uvicorn api:app --port 8000     # API on :8000 (separate terminal)
```

The UI and the API share one SQLite database (WAL mode), so uploads in one appear in the other. Data lives in `APP_DATA_DIR` (default `./data`) – back this folder up.

## Option 2 – Docker (files provided, not run in the build environment)

```bash
cp .env.example .env            # set API_KEY to a long random value
docker compose up --build
# UI:  http://localhost:8501     API: http://localhost:8000/docs
```

* One image, two services (`ui`, `api`) sharing the volume `docdata` mounted at `/data`.
* Tesseract is installed in the image; the app runs as a non-root user.
* Environment variables come from `.env`. **Never commit `.env`.**

## Option 3 – Streamlit Community Cloud (UI only)

1. Push this repository to GitHub.
2. Create an app pointing at `app.py`. `requirements.txt` and `packages.txt` (installs Tesseract) are picked up automatically.
3. Note: free cloud storage is temporary. Documents and the database are lost when the app restarts, so use this for demos only.

## Before real use

* Put the UI behind HTTPS and a login (reverse proxy or SSO). The Streamlit app has no login of its own.
* Set `API_KEY` for the API and serve it over HTTPS.
* Keep `MAX_FILE_MB`, `MAX_PDF_PAGES` at sensible limits for your users.
* Back up `APP_DATA_DIR` (database + stored files).
* Logs go to the console (`LOG_LEVEL` controls detail); raw errors are logged there and never shown to users.

## Checks after deployment

1. `GET /health` returns `{"status":"ok"}`.
2. Upload `sample_docs/invoice_harbor.pdf` – it should complete automatically.
3. Upload `sample_docs/scan_invoice_lakeside.png` – it should be read by OCR (if it says OCR is not installed, install Tesseract).
4. Ask the assistant *"What is the total amount on invoice HL-310?"* – expect `$800.00` with a source.
5. Restart the app – the documents and history are still there.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| "The OCR engine (Tesseract) is not installed" | Install `tesseract-ocr` (see Option 1) |
| `401 Missing or invalid API key` | Send `X-API-Key`, or leave `API_KEY` empty for local use |
| `413` on upload | File larger than `MAX_FILE_MB` |
| A document is stuck in *Processing* | It is returned to *New* automatically at the next start; run it again |
| "database is unavailable" | Check `APP_DATA_DIR` exists and is writable |
