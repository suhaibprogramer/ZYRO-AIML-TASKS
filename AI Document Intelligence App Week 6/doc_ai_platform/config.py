"""Central configuration.

Every setting can be overridden with an environment variable or a `.env` file
(see `.env.example`). Secrets such as API_KEY are read from the environment only
and are never stored in source code.

Other modules must read settings as `config.NAME` (not `from config import NAME`)
so tests and deployments can change them at run time.
"""
import logging
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_dotenv(path: Path) -> None:
    """Tiny .env reader (KEY=VALUE per line). Real environment variables win."""
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    except OSError:
        pass


_load_dotenv(BASE_DIR / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


# ---- locations -------------------------------------------------------------
DATA_DIR = os.environ.get("APP_DATA_DIR", str(BASE_DIR / "data"))
DB_PATH = os.environ.get("DB_PATH", os.path.join(DATA_DIR, "documents.db"))
STORAGE_ROOT = os.environ.get("STORAGE_ROOT", os.path.join(DATA_DIR, "storage"))
MODEL_PATH = os.environ.get("MODEL_PATH", str(BASE_DIR / "model.joblib"))  # optional trained classifier

# ---- upload protection -----------------------------------------------------
MAX_FILE_BYTES = int(_float("MAX_FILE_MB", 10) * 1024 * 1024)
MAX_PDF_PAGES = _int("MAX_PDF_PAGES", 50)
MAX_IMAGE_PIXELS = _int("MAX_IMAGE_PIXELS", 40_000_000)
OCR_TIMEOUT_SECONDS = _int("OCR_TIMEOUT_SECONDS", 60)

# ---- workflow and anomaly rules -------------------------------------------
CONFIDENCE_THRESHOLD = _float("CONFIDENCE_THRESHOLD", 0.60)  # only used if the classifier gives a probability
AMOUNT_TOLERANCE = _float("AMOUNT_TOLERANCE", 0.01)          # subtotal + tax vs total
OUTLIER_FACTOR = _float("OUTLIER_FACTOR", 10.0)              # total > factor x median of other invoices
OUTLIER_MIN_DOCS = _int("OUTLIER_MIN_DOCS", 4)               # need this many other invoices to judge

# ---- AI assistant (local retrieval, no external service) -------------------
CHUNK_CHARS = _int("CHUNK_CHARS", 300)
RAG_TOP_K = _int("RAG_TOP_K", 5)
RAG_MIN_SCORE = _float("RAG_MIN_SCORE", 0.10)       # minimum cosine similarity of the best chunk
RAG_MIN_COVERAGE = _float("RAG_MIN_COVERAGE", 0.50)  # share of question terms found in the documents

# ---- API -------------------------------------------------------------------
API_KEY = os.environ.get("API_KEY", "")  # empty = API open (local use); set it to require X-API-Key

# ---- logging ---------------------------------------------------------------
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
