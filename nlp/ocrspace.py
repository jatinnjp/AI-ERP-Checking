"""OCR.space API — free handwriting OCR (25,000 calls/month, no card)."""

import io
from typing import Tuple

import requests
from PIL import Image

from config import Config

OCR_URL = "https://api.ocr.space/parse/image"


def _ocr_one_page(pil_img: Image.Image, page_idx: int = 1) -> Tuple[str, float]:
    """OCR a single PIL image. Returns (text, confidence_in_[0,1])."""
    img = pil_img.convert("RGB")

    # Free tier max = 1 MB per file → resize if too big
    max_dim = 1600
    if max(img.size) > max_dim:
        ratio = max_dim / max(img.size)
        new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
        img = img.resize(new_size, Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    buf.seek(0)
    size_kb = len(buf.getvalue()) // 1024
    print(f"[ocrspace] Sending page {page_idx} ({size_kb} KB) ...")

    try:
        response = requests.post(
            OCR_URL,
            files={"page.jpg": ("page.jpg", buf, "image/jpeg")},
            data={
                "apikey": Config.OCRSPACE_API_KEY,
                "language": "eng",
                "OCREngine": "2",          # Engine 2 supports handwriting
                "scale": "true",
                "isTable": "false",
                "isOverlayRequired": "false",
                "detectOrientation": "true",
            },
            timeout=60,
        )
    except requests.RequestException as e:
        raise RuntimeError(f"OCR.space network error: {e}") from e

    if response.status_code != 200:
        raise RuntimeError(f"OCR.space HTTP {response.status_code}: {response.text[:200]}")

    data = response.json()

    if data.get("IsErroredOnProcessing"):
        msg = data.get("ErrorMessage") or data.get("ErrorDetails") or "Unknown error"
        if isinstance(msg, list):
            msg = " | ".join(msg)
        raise RuntimeError(f"OCR.space processing error: {msg}")

    parsed = data.get("ParsedResults") or []
    if not parsed:
        return "", 0.0

    text = parsed[0].get("ParsedText", "").strip()
    conf = 0.90 if text else 0.0
    return text, conf


def ocr_sheet_ocrspace(file_path: str) -> Tuple[str, float]:
    """Run OCR.space on an answer sheet (image or PDF)."""
    from nlp.preprocess import load_pages

    if not Config.OCRSPACE_API_KEY:
        raise RuntimeError("OCRSPACE_API_KEY is not set in .env")

    pages = load_pages(file_path)
    if not pages:
        return "", 0.0

    text_parts, confidences = [], []
    for idx, page in enumerate(pages, 1):
        try:
            text, conf = _ocr_one_page(page, idx)
            confidences.append(conf)
            text_parts.append(f"--- Page {idx} ---\n{text}\n")
            print(f"[ocrspace] Page {idx} OK ({len(text)} chars).")
        except Exception as e:
            print(f"[ocrspace] Page {idx} failed: {e}")
            text_parts.append(f"--- Page {idx} ---\n[OCR failed: {e}]\n")

    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    print(f"[ocrspace] Done. Avg confidence: {avg_conf:.2%}")
    return "\n".join(text_parts), avg_conf