"""Image preprocessing for handwritten answer sheets.

Two output modes:
    - prep_for_trocr(img) -> gentle grayscale (TrOCR likes natural images)
    - prep_for_easyocr(img) -> stronger contrast + denoise

Aggressive binarization is AVOIDED for TrOCR because the
microsoft/trocr-*-handwritten models were trained on natural
grayscale photos (IAM dataset) and lose accuracy on hard binary input.
"""

from pathlib import Path
from typing import List

import cv2
import numpy as np
from PIL import Image


def _deskew(gray: np.ndarray) -> np.ndarray:
    coords = np.column_stack(np.where(gray < 200))
    if len(coords) < 50:
        return gray
    angle = cv2.minAreaRect(coords)[-1]
    angle = -(90 + angle) if angle < -45 else -angle
    if abs(angle) < 0.5:
        return gray
    h, w = gray.shape
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    return cv2.warpAffine(gray, M, (w, h),
                          flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REPLICATE)


def prep_for_trocr(pil_img: Image.Image) -> Image.Image:
    """Gentle preprocessing — keep natural grayscale; no binarization."""
    img = np.array(pil_img.convert("RGB"))
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    # Mild denoise only
    denoised = cv2.fastNlMeansDenoising(gray, h=7)
    deskewed = _deskew(denoised)
    # Convert back to RGB so TrOCR's processor accepts it
    rgb = cv2.cvtColor(deskewed, cv2.COLOR_GRAY2RGB)
    return Image.fromarray(rgb)


def prep_for_easyocr(pil_img: Image.Image) -> Image.Image:
    """Stronger preprocessing — boost contrast for CNN-based EasyOCR."""
    img = np.array(pil_img.convert("RGB"))
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    enhanced = clahe.apply(denoised)
    deskewed = _deskew(enhanced)
    rgb = cv2.cvtColor(deskewed, cv2.COLOR_GRAY2RGB)
    return Image.fromarray(rgb)


def load_pages(file_path: str) -> List[Image.Image]:
    """Load image or PDF as a list of *raw* PIL pages (no preprocessing yet)."""
    path = Path(file_path)
    ext = path.suffix.lower().lstrip(".")
    if ext == "pdf":
        from pdf2image import convert_from_path
        return convert_from_path(str(path), dpi=300)
    return [Image.open(path)]