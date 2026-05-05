"""NLP package: OCR + LLM cleanup + fine-tuned BERT grader.

All models are lazily loaded on first call (singleton pattern).
The Flask app starts instantly; the first OCR upload triggers
the download/load (~720 MB total, cached after that).
"""