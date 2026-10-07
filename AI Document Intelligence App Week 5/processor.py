"""PDF/image reading, OCR and text processing."""
import io
import re

MIN_TEXT_CHARS = 20  # fewer characters than this = treat as unreadable


class ProcessingError(Exception):
    """The file is corrupt or cannot be opened at all (message is safe to show)."""


def clean_text(text: str) -> str:
    text = (text or "").replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _ocr_image(img) -> str:
    try:
        import pytesseract
        from PIL import ImageOps
        gray = ImageOps.autocontrast(ImageOps.grayscale(img))
        if gray.width < 1000:
            ratio = 1000 / gray.width
            gray = gray.resize((1000, int(gray.height * ratio)))
        return pytesseract.image_to_string(gray)
    except Exception:
        return ""  # OCR engine missing/failed: caller treats as no text


def extract_text(data: bytes, filename: str) -> str:
    """Return cleaned text. Raises ProcessingError for corrupt files.

    An empty string means the file opened fine but nothing readable was found
    (e.g. a blank or very poor scan) - the workflow sends that to review.
    """
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext == "pdf":
        try:
            import pymupdf
            doc = pymupdf.open(stream=data, filetype="pdf")
        except Exception as exc:
            raise ProcessingError("The PDF is corrupt or cannot be opened.") from exc
        try:
            text = "\n".join(page.get_text() for page in doc)
            if len(text.strip()) < MIN_TEXT_CHARS:  # scanned PDF -> OCR fallback
                from PIL import Image
                parts = []
                for page in doc:
                    pix = page.get_pixmap(dpi=200)
                    parts.append(_ocr_image(Image.open(io.BytesIO(pix.tobytes("png")))))
                text = "\n".join(parts)
        finally:
            doc.close()
        return clean_text(text)
    if ext in ("png", "jpg", "jpeg"):
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(data))
            img.load()
        except Exception as exc:
            raise ProcessingError("The image is corrupt or cannot be opened.") from exc
        return clean_text(_ocr_image(img))
    raise ProcessingError("Unsupported file type.")


def has_readable_text(text: str) -> bool:
    return len((text or "").strip()) >= MIN_TEXT_CHARS
