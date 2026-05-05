"""BERT-based semantic grader (the project's USP).

If a fine-tuned model exists at Config.GRADER_FINETUNED_PATH, it is used.
Otherwise we fall back to the base sentence-transformer.
"""

from typing import Dict

from config import Config

_model = None
_model_source = None


def _get_model():
    global _model, _model_source
    if _model is None:
        from sentence_transformers import SentenceTransformer
        if Config.GRADER_FINETUNED_PATH.exists():
            print(f"[grader] Loading FINE-TUNED model from {Config.GRADER_FINETUNED_PATH}")
            _model = SentenceTransformer(str(Config.GRADER_FINETUNED_PATH))
            _model_source = "fine-tuned"
        else:
            print(f"[grader] No fine-tuned model found. Using base: {Config.GRADER_BASE_MODEL}")
            _model = SentenceTransformer(Config.GRADER_BASE_MODEL)
            _model_source = "base"
    return _model


def grader_info() -> str:
    _get_model()
    return _model_source or "unknown"


def _keyword_overlap(student: str, reference: str) -> float:
    """Bonus signal: fraction of important reference words present in student answer.
    Helps when OCR garbles a few letters but key concepts are still recognisable.
    """
    import re
    stop = {
        "the", "a", "an", "is", "are", "was", "were", "and", "or", "but",
        "of", "to", "in", "on", "at", "by", "for", "with", "from", "as",
        "it", "this", "that", "these", "those", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "can",
    }
    def keywords(text):
        words = re.findall(r"[a-zA-Z]{3,}", text.lower())
        return {w for w in words if w not in stop}

    ref_kw = keywords(reference)
    stu_kw = keywords(student)
    if not ref_kw:
        return 0.0

    # Allow fuzzy match: any reference keyword that appears (even with 1-char OCR error)
    matched = 0
    for r in ref_kw:
        if r in stu_kw:
            matched += 1
            continue
        # Fuzzy: any student word starts/ends with same 4 chars
        for s in stu_kw:
            if len(r) >= 5 and len(s) >= 5 and (r[:4] == s[:4] or r[-4:] == s[-4:]):
                matched += 1
                break
    return matched / len(ref_kw)


def grade(student_answer: str, reference_answer: str, max_marks: float = 10.0) -> Dict:
    """Score a single answer with combined semantic + keyword signal.

    Combines:
        - BERT cosine similarity (60% weight)
        - Keyword overlap         (40% weight)

    This makes grading robust to OCR errors: if "photosynthesis" is misread
    as "phslsyates" the keyword check fails, but if "process / plants /
    sunlight / glucose / oxygen" all show up correctly the score is fair.
    """
    if not student_answer.strip() or not reference_answer.strip():
        return {"score": 0.0, "similarity": 0.0, "max_marks": max_marks, "model": grader_info()}

    model = _get_model()
    from sentence_transformers import util

    embeddings = model.encode(
        [student_answer.strip(), reference_answer.strip()],
        convert_to_tensor=True, show_progress_bar=False,
    )
    sim = float(util.cos_sim(embeddings[0], embeddings[1]).item())
    sim = max(0.0, min(1.0, sim))

    keyword = _keyword_overlap(student_answer, reference_answer)

    # Combine: 60% semantic, 40% keyword overlap
    combined = 0.6 * sim + 0.4 * keyword

    # More forgiving curve: 0.2 -> 0, 0.75 -> full
    if combined < 0.2:
        scaled = 0.0
    elif combined > 0.75:
        scaled = 1.0
    else:
        scaled = (combined - 0.2) / 0.55

    score = round(scaled * max_marks, 2)
    return {
        "score": score,
        "similarity": round(sim, 4),
        "max_marks": max_marks,
        "model": grader_info(),
    }