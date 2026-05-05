"""Centralised configuration loaded from environment variables."""

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


class Config:
    # ----- Flask -----
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
    DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"

    # ----- SQLite -----
    DATABASE_PATH = BASE_DIR / os.getenv("DATABASE_PATH", "app.db")

    # ----- File uploads -----
    UPLOAD_FOLDER = BASE_DIR / os.getenv("UPLOAD_FOLDER", "uploads")
    MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "10"))
    MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf"}

    # ----- NLP models -----
    TROCR_MODEL = os.getenv("TROCR_MODEL", "microsoft/trocr-base-handwritten")
    LLM_MODEL = os.getenv("LLM_MODEL", "google/flan-t5-base")
    GRADER_BASE_MODEL = os.getenv(
        "GRADER_BASE_MODEL",
        "sentence-transformers/paraphrase-MiniLM-L6-v2",
    )
    GRADER_FINETUNED_PATH = BASE_DIR / os.getenv(
        "GRADER_FINETUNED_PATH", "models/sbert-grading-finetuned"
    )

    # ----- OCR -----
    OCR_MIN_CONFIDENCE = float(os.getenv("OCR_MIN_CONFIDENCE", "0.40"))
    USE_TROCR = os.getenv("USE_TROCR", "0") == "1"
    USE_GCP_VISION = os.getenv("USE_GCP_VISION", "0") == "1"
    GCP_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "gcp-credentials.json")
    USE_OCRSPACE = os.getenv("USE_OCRSPACE", "0") == "1"
    OCRSPACE_API_KEY = os.getenv("OCRSPACE_API_KEY", "")

# Make sure required folders exist
Config.UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
(BASE_DIR / "models").mkdir(parents=True, exist_ok=True)