"""Google Cloud Vision API — handwriting OCR.

Uses DOCUMENT_TEXT_DETECTION which is Google's specialized model for
dense handwritten text.

Free tier: 1000 requests / month.
"""

import os
from pathlib import Path
from typing import List, Tuple

from PIL import Image

from config import Config


_client = None


def _get_client():
    """Lazy-init the Vision API client."""
    global _client
    if _client is None:
        # Tell the SDK where to find the credentials JSON
        cred_path = Path(Config.GCP_CREDENTIALS)
        if not cred_path.is_absolute():
            cred_path = Path(__file__).resolve().parent.parent / cred_path
        if not cred_path.exists():
            raise FileNotFoundError(
                f"GCP credentials not found at {cred_path}. "
                "Set GOOGLE_APPLICATION_CREDENTIALS in .env to point to your JSON key file."
            )
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(cred_path)

        from google.cloud import vision
        _client = vision.ImageAnnotatorClient()
        print(f"[gcp] Vision API client ready (creds: {cred_path.name})")
    return _client


def _ocr_one_page(pil_img: Image.Image) -> Tuple[str, float]:
    """OCR a single PIL image. Returns (text, average_confidence_in_[0,1])."""
    from google.cloud import vision
    import io

    # Encode image as PNG bytes
    buf = io.BytesIO()
    pil_img.convert("RGB").save(buf, format="PNG")
    image = vision.Image(content=buf.getvalue())

    # DOCUMENT_TEXT_DETECTION is Google's handwriting-specialized model
    response = _get_client().document_text_detection(
        image=image,
        image_context={"language_hints": ["en"]},
    )
    if response.error.message:
        raise RuntimeError(f"GCP Vision API error: {response.error.message}")

    full_text = response.full_text_annotation.text or ""

    # Average word-level confidence
    confidences = []
    for page in response.full_text_annotation.pages:
        for block in page.blocks:
            for paragraph in block.paragraphs:
                for word in paragraph.words:
                    if word.confidence:
                        confidences.append(word.confidence)

    avg_conf = sum(confidences) / len(confidences) if confidences else 0.9
    return full_text.strip(), avg_conf


def ocr_sheet_gcp(file_path: str) -> Tuple[str, float]:
    """Run GCP Vision OCR on an answer sheet (image or PDF)."""
    from nlp.preprocess import load_pages

    pages = load_pages(file_path)
    if not pages:
        return "", 0.0

    text_parts, confidences = [], []
    for idx, page in enumerate(pages, 1):
        print(f"[gcp] OCR page {idx}/{len(pages)} ...")
        try:
            text, conf = _ocr_one_page(page)
            confidences.append(conf)
            text_parts.append(f"--- Page {idx} ---\n{text}\n")
        except Exception as e:
            print(f"[gcp] page {idx} failed: {e}")
            text_parts.append(f"--- Page {idx} ---\n[OCR failed: {e}]\n")

    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    print(f"[gcp] Done. Avg confidence: {avg_conf:.2%}")
    return "\n".join(text_parts), avg_conf