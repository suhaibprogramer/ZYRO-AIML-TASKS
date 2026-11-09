"""PDF / image reading, integrity checks, OCR and text preparation."""
import io
import re
import threading
from collections import OrderedDict

import config
import storage

MIN_TEXT_CHARS = 20  # fewer characters than this = treat as unreadable

_CACHE_SIZE = 32
_cache: "OrderedDict[str, tuple]" = OrderedDict()  # file hash -> (text, method); reuses OCR work
_cache_lock = threading.Lock()
cache_stats = {"hits": 0, "misses": 0}


class ProcessingError(Exception):
    """The file is corrupt, unsafe or cannot be read. The message is safe to show.

    `code` is used by the API: corrupt, too_many_pages, too_large_image, ocr_unavailable, unsupported.
    """

    def __init__(self, message: str, code: str = "corrupt"):
        super().__init__(message)
        self.code = code


def clean_text(text: str) -> str:
    text = (text or "").replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _ext(filename: str) -> str:
    return filename.lower().rsplit(".", 1)[-1] if "." in filename else ""


def _open_pdf(data: bytes):
    import pymupdf
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ProcessingError("The PDF is corrupt or cannot be opened.", "corrupt") from exc
    if doc.needs_pass:
        doc.close()
        raise ProcessingError("The PDF is password-protected and cannot be processed.", "corrupt")
    if doc.page_count == 0:
        doc.close()
        raise ProcessingError("The PDF has no pages.", "corrupt")
    if doc.page_count > config.MAX_PDF_PAGES:
        count = doc.page_count
        doc.close()
        raise ProcessingError(f"The PDF has {count} pages; the limit is {config.MAX_PDF_PAGES}.",
                              "too_many_pages")
    return doc


def _open_image(data: bytes):
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = config.MAX_IMAGE_PIXELS
    try:
        Image.open(io.BytesIO(data)).verify()          # structure check
        img = Image.open(io.BytesIO(data))              # verify() leaves the file unusable, so reopen
        img.load()
    except Exception as exc:
        raise ProcessingError("The image is corrupt or cannot be opened.", "corrupt") from exc
    if img.width * img.height > config.MAX_IMAGE_PIXELS:
        raise ProcessingError("The image is too large to process safely.", "too_large_image")
    return img


def check_integrity(data: bytes, filename: str) -> None:
    """Basic document integrity check run at upload, before anything is stored."""
    ext = _ext(filename)
    if ext == "pdf":
        _open_pdf(data).close()
    elif ext in ("png", "jpg", "jpeg"):
        _open_image(data)
    else:
        raise ProcessingError("Unsupported file type.", "unsupported")


def _ocr_image(img) -> str:
    """OCR with light preprocessing (grayscale, contrast, upscale small images)."""
    try:
        import pytesseract
        from PIL import ImageOps
        gray = ImageOps.autocontrast(ImageOps.grayscale(img))
        if gray.width < 1000:
            gray = gray.resize((1000, int(gray.height * 1000 / gray.width)))
        return pytesseract.image_to_string(gray, timeout=config.OCR_TIMEOUT_SECONDS)
    except ImportError as exc:
        raise ProcessingError("OCR is not installed on this server.", "ocr_unavailable") from exc
    except Exception as exc:
        name = type(exc).__name__
        if name == "TesseractNotFoundError":
            raise ProcessingError("The OCR engine (Tesseract) is not installed on this server.",
                                  "ocr_unavailable") from exc
        if isinstance(exc, RuntimeError):  # pytesseract raises RuntimeError on timeout
            raise ProcessingError("OCR took too long on this file.", "ocr_unavailable") from exc
        raise ProcessingError("The text in this image could not be read.", "corrupt") from exc


def read_document(data: bytes, filename: str):
    """Return (cleaned text, method) where method is 'pdf-text' or 'ocr'.

    Results are cached by content hash so the same file is never OCR'd twice in a
    process. An empty string means the file opened fine but nothing readable was found.
    """
    key = storage.sha256_bytes(data)
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            cache_stats["hits"] += 1
            return _cache[key]
        cache_stats["misses"] += 1

    ext = _ext(filename)
    if ext == "pdf":
        doc = _open_pdf(data)
        try:
            text, method = "\n".join(page.get_text() for page in doc), "pdf-text"
            if len(text.strip()) < MIN_TEXT_CHARS:  # scanned PDF -> OCR each page
                from PIL import Image
                parts = [_ocr_image(Image.open(io.BytesIO(page.get_pixmap(dpi=200).tobytes("png"))))
                         for page in doc]
                text, method = "\n".join(parts), "ocr"
        finally:
            doc.close()
    elif ext in ("png", "jpg", "jpeg"):
        text, method = _ocr_image(_open_image(data)), "ocr"
    else:
        raise ProcessingError("Unsupported file type.", "unsupported")

    result = (clean_text(text), method)
    with _cache_lock:
        _cache[key] = result
        while len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
    return result


def extract_text(data: bytes, filename: str) -> str:
    return read_document(data, filename)[0]


def has_readable_text(text: str) -> bool:
    return len((text or "").strip()) >= MIN_TEXT_CHARS
