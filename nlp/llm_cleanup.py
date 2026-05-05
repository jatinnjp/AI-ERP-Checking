"""OCR cleanup + per-question segmentation.

Strategy:
    - For CLOUD OCR (GCP / OCR.space): skip Flan-T5 cleanup; text is already clean.
    - Segmentation: regex with smart fallback for bare markers (Ans- without number).
"""

import re
from typing import Dict, List, Tuple

from config import Config

_tokenizer = None
_model = None


def _get_llm():
    global _tokenizer, _model
    if _model is None:
        print(f"[llm] Loading {Config.LLM_MODEL} ...")
        from transformers import T5ForConditionalGeneration, T5Tokenizer
        _tokenizer = T5Tokenizer.from_pretrained(Config.LLM_MODEL)
        _model = T5ForConditionalGeneration.from_pretrained(Config.LLM_MODEL)
        _model.eval()
        print("[llm] Flan-T5 ready.")
    return _tokenizer, _model


def _generate(prompt: str, max_new_tokens: int = 512) -> str:
    tokenizer, model = _get_llm()
    import torch
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=1024)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=max_new_tokens,
                             num_beams=4, no_repeat_ngram_size=3)
    return tokenizer.decode(out[0], skip_special_tokens=True)


def clean_ocr_text(raw_text: str) -> str:
    """Strip pipeline metadata; skip Flan-T5 for cloud OCR (already clean)."""
    if not raw_text.strip():
        return ""

    stripped = re.sub(r"\[(TrOCR|EasyOCR)\]|--- Page \d+ ---", " ", raw_text)
    stripped = re.sub(r"[ \t]+", " ", stripped)
    stripped = re.sub(r"\n{2,}", "\n", stripped).strip()

    if Config.USE_GCP_VISION or Config.USE_OCRSPACE:
        return stripped

    prompt = (
        "Fix OCR errors in this student answer text. Preserve all answer "
        "markers like Ans1, Ans-1, Q1, A1. Do not add new content. "
        "Return only the corrected text.\n\n"
        f"Text: {stripped}"
    )
    try:
        out = _generate(prompt, max_new_tokens=512).strip()
        return out or stripped
    except Exception as e:
        print(f"[llm] cleanup failed, returning raw: {e}")
        return stripped


# ----------- Segmentation -----------
# Marker WITH number: Ans1, Ans-1, Q1, A1, Question 1, 1) , 1.
_MARKER_NUMBERED = re.compile(
    r"\b(?:"
    r"(?:Q(?:uestion|ues|ue)?|A(?:ns(?:wer)?)?)\s*[-.:)]?\s*(\d+)"
    r"|(\d+)\s*[)\.]"
    r")\s*[:.\)\-]?\s*",
    re.IGNORECASE,
)

# Marker WITHOUT number (bare): "Ans-", "Ans:", "Ans.", "Q.", "Answer:"
_MARKER_BARE = re.compile(
    r"\b(?:Q(?:uestion|ues|ue)?|A(?:ns(?:wer)?))\s*[-.:]\s*(?!\d)",
    re.IGNORECASE,
)


def segment_by_question(cleaned_text: str, question_count: int) -> Dict[int, str]:
    if not cleaned_text.strip() or question_count < 1:
        return {}

    parsed = _split_by_markers(cleaned_text, question_count)

    # Backfill missing
    for i in range(1, question_count + 1):
        parsed.setdefault(i, "")

    # If everything is empty, fall back to even-split
    if sum(len(v.strip()) for v in parsed.values()) < 5:
        return _split_evenly(cleaned_text, question_count)

    return parsed


def _split_by_markers(text: str, expected: int) -> Dict[int, str]:
    """Find all markers (numbered + bare). Assign bare ones sequentially
    to fill missing slots."""
    # Collect all markers with their position and (maybe) number
    markers: List[Tuple[int, int, int]] = []  # (start, end, number_or_0)

    for m in _MARKER_NUMBERED.finditer(text):
        n = int(m.group(1) or m.group(2))
        if 1 <= n <= expected:
            markers.append((m.start(), m.end(), n))

    for m in _MARKER_BARE.finditer(text):
        # Skip if this position is already covered by a numbered marker
        overlap = any(s <= m.start() < e for s, e, _ in markers)
        if not overlap:
            markers.append((m.start(), m.end(), 0))  # 0 = unknown number

    if not markers:
        return {}

    # Sort by position
    markers.sort(key=lambda x: x[0])

    # Assign numbers to bare markers: fill missing slots in order
    used = {n for _, _, n in markers if n > 0}
    available = [i for i in range(1, expected + 1) if i not in used]
    avail_idx = 0

    final: List[Tuple[int, int, int]] = []
    for s, e, n in markers:
        if n == 0:
            if avail_idx < len(available):
                n = available[avail_idx]
                avail_idx += 1
            else:
                continue  # No slot left, skip
        final.append((s, e, n))

    if not final:
        return {}

    final.sort(key=lambda x: x[0])  # sort again by position

    # Extract content between markers
    out: Dict[int, str] = {}
    for i, (_, end, n) in enumerate(final):
        next_start = final[i + 1][0] if i + 1 < len(final) else len(text)
        body = text[end:next_start].strip(" \n.:-")
        # Remove stray digits/punctuation at the start (e.g. orphan "1" from "Ans- 1")
        body = re.sub(r"^[\d\s.:\-)]+", "", body).strip()
        if n not in out or len(body) > len(out[n]):
            out[n] = body
    return out


def _split_evenly(text: str, n: int) -> Dict[int, str]:
    words = text.split()
    if not words:
        return {i: "" for i in range(1, n + 1)}
    chunk = max(1, len(words) // n)
    return {i + 1: " ".join(words[i * chunk:(i + 1) * chunk]) for i in range(n)}