# AI Answer Sheet Evaluation System

An automated grading system for handwritten student answer sheets. Uses **Google Cloud Vision** for OCR, **SBERT** for semantic similarity scoring, and a **Flask + SQLite** web app for student/teacher workflows.

---

## 🚀 Quick Start (for new contributors)

### Prerequisites
- **Python 3.10+** ([download](https://www.python.org/downloads/))
- **Git**
- **Poppler** (for PDF support — Windows: [download](https://github.com/oschwartz10612/poppler-windows/releases/), add `bin/` to PATH)
- A **Google Cloud Vision API** service-account JSON OR an **OCR.space** free API key

---

### 1. Clone the repo

```bash
git clone https://github.com/<your-username>/AI-ERP-Checking.git
cd AI-ERP-Checking
```

### 2. Create a virtual environment

**Windows (PowerShell):**
```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

**Linux / macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

> ⏱️ This takes ~5 minutes (downloads PyTorch, transformers, sentence-transformers, etc.)

### 4. Set up environment variables

Copy the template and fill in your values:

```bash
# Windows
copy .env.example .env

# Linux / macOS
cp .env.example .env
```

Then **open `.env`** and configure ONE of the OCR options (see next section).

### 5. Set up OCR credentials

#### Option A — Google Cloud Vision (recommended, best accuracy)

1. Get a **Vision API enabled** GCP project with billing active.
2. Create a service account → download the JSON key.
3. Place the JSON file at the project root and rename it to **`gcp-credentials.json`**.
4. In `.env`, set:
   ```
   USE_GCP_VISION=1
   USE_OCRSPACE=0
   GOOGLE_APPLICATION_CREDENTIALS=gcp-credentials.json
   ```

#### Option B — OCR.space (free, no credit card)

1. Sign up at https://ocr.space/ocrapi/freekey (just an email — gets you 25,000 free OCR calls/month).
2. In `.env`, set:
   ```
   USE_GCP_VISION=0
   USE_OCRSPACE=1
   OCRSPACE_API_KEY=your-key-from-the-email
   ```

### 6. Initialize the database (first run only)

```bash
python -c "from app import db, app; app.app_context().push(); db.create_all(); print('DB created')"
```

### 7. Run the app

```bash
python app.py
```

Open: **http://127.0.0.1:5000**

---

## 👤 Default Logins (seeded)

| Role    | Username      | Password   |
|---------|---------------|------------|
| Teacher | `teacher1`    | `teacher123` |
| Student | `student1`    | `student123` |

> Change these after first login OR re-seed via `scripts/seed_users.py` if it exists.

---

## 📁 Project Structure

```
AI-ERP-Checking/
├── app.py                    # Flask entry point
├── config.py                 # Config & feature flags
├── requirements.txt
├── .env.example              # Template for environment vars
├── routes/                   # Flask blueprints (auth, student, teacher)
├── nlp/
│   ├── ocr.py                # OCR dispatcher
│   ├── gcp_ocr.py            # Google Cloud Vision client
│   ├── ocrspace.py           # OCR.space client
│   ├── llm_cleanup.py        # Text cleanup + question segmentation
│   ├── grader.py             # SBERT-based similarity scorer
│   └── preprocess.py         # Image preprocessing & PDF page loading
├── models/
│   └── finetuned-sbert/      # (optional) custom-trained grader model
├── data/
│   ├── training_pairs.csv    # SBERT fine-tuning data
│   └── eval_pairs.csv
├── scripts/
│   ├── build_dataset.py      # Generate training pairs
│   ├── finetune_sbert.py     # Train custom grader
│   └── evaluate_grader.py    # Compare base vs fine-tuned
├── templates/                # Jinja HTML templates
├── static/                   # CSS, images, JS
└── uploads/                  # Student-uploaded answer sheets (gitignored)
```

---

## 🧠 (Optional) Train Your Own Grader

The default grader is `paraphrase-MiniLM-L6-v2`. For better domain-specific scoring:

```bash
python scripts/build_dataset.py        # ~5 sec
python scripts/finetune_sbert.py       # ~10–15 min on CPU
python scripts/evaluate_grader.py      # see before/after metrics
```

The fine-tuned model is auto-loaded by `nlp/grader.py` if `models/finetuned-sbert/` exists.

---

## 🐛 Troubleshooting

| Error | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'X'` | `pip install -r requirements.txt` (make sure venv is active) |
| `403 BILLING_DISABLED` | GCP project's billing is off — enable billing or switch to OCR.space (Option B) |
| `pdf2image: Unable to get page count` | Install Poppler and add to PATH |
| `OCR confidence too low (0.00)` | OCR engine threw an error — check terminal for the real error above the message |
| `[grader] No fine-tuned model found` | Either run `scripts/finetune_sbert.py`, or ignore — uses the base model |

---

## 📜 License

MIT (or whatever you prefer)