"""OCR pipeline (CPU-friendly).

Two modes controlled by Config.USE_TROCR:
    - False (default on CPU): EasyOCR only — fast (~10-20s per page).
    - True : EasyOCR + TrOCR re-reads low-confidence boxes — slower but
             slightly more accurate (~1-3 min per page on CPU).
"""

from typing import List, Tuple

import numpy as np
from PIL import Image

from config import Config
from nlp.preprocess import load_pages, prep_for_easyocr, prep_for_trocr

_trocr_processor = None
_trocr_model = None
_easyocr_reader = None

TROCR_BATCH_SIZE = 8
TROCR_RECHECK_THRESHOLD = 0.95


def _get_trocr():
    global _trocr_processor, _trocr_model
    if _trocr_model is None:
        print(f"[ocr] Loading TrOCR ({Config.TROCR_MODEL}) ...")
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel
        _trocr_processor = TrOCRProcessor.from_pretrained(Config.TROCR_MODEL)
        _trocr_model = VisionEncoderDecoderModel.from_pretrained(Config.TROCR_MODEL)
        _trocr_model.eval()
        print("[ocr] TrOCR ready.")
    return _trocr_processor, _trocr_model


def _get_easyocr():
    global _easyocr_reader
    if _easyocr_reader is None:
        print("[ocr] Loading EasyOCR ...")
        import easyocr
        _easyocr_reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        print("[ocr] EasyOCR ready.")
    return _easyocr_reader


def _trocr_batch(crops: List[Image.Image]) -> List[str]:
    if not crops:
        return []
    processor, model = _get_trocr()
    import torch

    valid_idx, valid_imgs = [], []
    for i, c in enumerate(crops):
        if c.width >= 20 and c.height >= 10:
            valid_idx.append(i)
            valid_imgs.append(c.convert("RGB"))

    results = [""] * len(crops)
    if not valid_imgs:
        return results

    for start in range(0, len(valid_imgs), TROCR_BATCH_SIZE):
        chunk = valid_imgs[start:start + TROCR_BATCH_SIZE]
        chunk_idx = valid_idx[start:start + TROCR_BATCH_SIZE]
        pixel_values = processor(images=chunk, return_tensors="pt").pixel_values
        with torch.no_grad():
            ids = model.generate(pixel_values, max_length=128, num_beams=1)
        decoded = processor.batch_decode(ids, skip_special_tokens=True)
        for i, txt in zip(chunk_idx, decoded):
            results[i] = txt.strip()
    return results


def ocr_sheet(file_path: str) -> Tuple[str, float]:
    # If OCR.space is enabled, route everything there and skip local OCR
    if Config.USE_OCRSPACE:
        from nlp.ocrspace import ocr_sheet_ocrspace
        return ocr_sheet_ocrspace(file_path)

    if Config.USE_GCP_VISION:
        from nlp.gcp_ocr import ocr_sheet_gcp
        return ocr_sheet_gcp(file_path)


    raw_pages = load_pages(file_path)
    if not raw_pages:
        return "", 0.0

    output_parts, all_conf = [], []

    for page_idx, raw_page in enumerate(raw_pages, 1):
        easy_img = prep_for_easyocr(raw_page)

        # 1) EasyOCR detect+read
        try:
            print(f"[ocr] EasyOCR reading page {page_idx} ...")
            easy_results = _get_easyocr().readtext(
                np.array(easy_img.convert("RGB")), detail=1, paragraph=False
            )
            print(f"[ocr] EasyOCR found {len(easy_results)} text regions.")
        except Exception as e:
            print(f"[ocr] EasyOCR failed page {page_idx}: {e}")
            easy_results = []

        easy_lines = []
        for bbox, text, conf in easy_results:
            all_conf.append(float(conf))
            easy_lines.append(text.strip())

        merged = list(easy_lines)

        # 2) Optional TrOCR re-read on low-confidence boxes
        if Config.USE_TROCR and easy_results:
            trocr_img = prep_for_trocr(raw_page)
            trocr_np = np.array(trocr_img)
            crops, idx_map = [], []
            for i, (bbox, text, conf) in enumerate(easy_results):
                if conf < TROCR_RECHECK_THRESHOLD:
                    try:
                        xs = [int(p[0]) for p in bbox]
                        ys = [int(p[1]) for p in bbox]
                        x1, x2 = max(0, min(xs) - 4), min(trocr_np.shape[1], max(xs) + 4)
                        y1, y2 = max(0, min(ys) - 4), min(trocr_np.shape[0], max(ys) + 4)
                        crops.append(Image.fromarray(trocr_np[y1:y2, x1:x2]))
                        idx_map.append(i)
                    except Exception as e:
                        print(f"[ocr] crop failed: {e}")
            if crops:
                print(f"[ocr] TrOCR re-reading {len(crops)} low-confidence boxes ...")
                trocr_texts = _trocr_batch(crops)
                for i, txt in zip(idx_map, trocr_texts):
                    if txt:
                        merged[i] = txt

        page_text = (
            f"--- Page {page_idx} ---\n"
            + "\n".join(merged)
            + "\n"
        )
        output_parts.append(page_text)

    avg_conf = float(np.mean(all_conf)) if all_conf else 0.0
    return "\n".join(output_parts), avg_conf