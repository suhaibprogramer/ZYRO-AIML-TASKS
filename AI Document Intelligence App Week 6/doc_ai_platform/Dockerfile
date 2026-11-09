# One image runs both the Streamlit UI and the REST API (choose with the command).
FROM python:3.12-slim

# Tesseract is needed to read scanned images
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./
# Run as a non-root user; /data holds the database and uploaded files (mount a volume here)
RUN useradd --create-home appuser && mkdir /data && chown appuser /data
USER appuser
ENV APP_DATA_DIR=/data

EXPOSE 8501 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
