"""
Image preprocessing to improve OCR results on scanned or low-quality
documents: grayscale conversion, resizing, thresholding, and light noise
reduction.
"""

import numpy as np
from PIL import Image

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


def preprocess_for_ocr(pil_image: Image.Image, upscale_if_small: bool = True) -> Image.Image:
    """
    Apply beginner-friendly preprocessing to improve OCR accuracy:
    1. Convert to grayscale
    2. Upscale small images (OCR struggles on low-resolution scans)
    3. Denoise slightly
    4. Apply adaptive thresholding (binarization)

    Falls back to plain grayscale (PIL-only) if OpenCV isn't available.
    """
    if not CV2_AVAILABLE:
        return pil_image.convert("L")

    img = np.array(pil_image.convert("RGB"))
    img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    if upscale_if_small and (img.shape[0] < 1000 or img.shape[1] < 1000):
        scale = 2
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    img = cv2.fastNlMeansDenoising(img, h=10)

    img = cv2.adaptiveThreshold(
        img, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=31,
        C=15,
    )

    return Image.fromarray(img)
