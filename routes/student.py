"""Student routes — upload sheet + view results.

URL prefix: /student
All routes require role='student'.

This is where the full pipeline runs synchronously:
    upload -> preprocess -> OCR -> LLM cleanup -> segment -> grade -> save
"""

import json
import traceback
from pathlib import Path

from flask import (
    Blueprint, current_app, flash, redirect, render_template,
    request, send_file, session, url_for,
)
from werkzeug.utils import secure_filename

from auth.decorators import role_required
from config import Config
from db import execute, query_all, query_one

student_bp = Blueprint("student", __name__)


def _allowed(filename: str) -> bool:
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in Config.ALLOWED_EXTENSIONS
    )


# -------------------------------------------------------------------- #
# Dashboard                                                            #
# -------------------------------------------------------------------- #
@student_bp.route("/home")
@role_required("student")
def home():
    # All tests (any teacher) — students can attempt any test
    tests = query_all(
        "SELECT t.test_id, t.test_name, u.username AS teacher_name, "
        "       (SELECT COUNT(*) FROM Questions q WHERE q.test_id=t.test_id) AS qcount, "
        "       (SELECT COUNT(*) FROM AnswerSheets s WHERE s.test_id=t.test_id AND s.student_id=?) AS my_sheets "
        "FROM Tests t JOIN Users u ON u.user_id=t.created_by "
        "ORDER BY t.test_id DESC",
        (session["user_id"],),
    )
    return render_template("student/home.html", tests=tests)


# -------------------------------------------------------------------- #
# Upload + grade pipeline                                              #
# -------------------------------------------------------------------- #
@student_bp.route("/upload/<int:test_id>", methods=["GET", "POST"])
@role_required("student")
def upload_sheet(test_id: int):
    test = query_one("SELECT * FROM Tests WHERE test_id=?", (test_id,))
    if not test:
        flash("Test not found.", "danger")
        return redirect(url_for("student.home"))

    questions = query_all(
        "SELECT q.question_id, q.question_text, q.max_marks, q.question_order, "
        "       (SELECT answer_text FROM ExpectedAnswers ea "
        "        WHERE ea.question_id=q.question_id ORDER BY ea.answer_id LIMIT 1) AS reference_answer "
        "FROM Questions q WHERE q.test_id=? ORDER BY q.question_order",
        (test_id,),
    )
    if not questions:
        flash("This test has no questions yet. Ask the teacher to add some.", "warning")
        return redirect(url_for("student.home"))

    if request.method == "POST":
        f = request.files.get("answer_sheet")
        if not f or f.filename == "":
            flash("Please choose a file.", "danger")
            return redirect(request.url)
        if not _allowed(f.filename):
            flash("Unsupported file type. Allowed: PNG, JPG, JPEG, PDF.", "danger")
            return redirect(request.url)

        filename = secure_filename(f.filename)
        ext = filename.rsplit(".", 1)[1].lower()
        file_type = "pdf" if ext == "pdf" else "image"

        # Save under uploads/<student_id>/
        student_dir = Path(Config.UPLOAD_FOLDER) / str(session["user_id"])
        student_dir.mkdir(parents=True, exist_ok=True)

        # Insert sheet record first to get an id
        sheet_id = execute(
            "INSERT INTO AnswerSheets "
            "(student_id, test_id, file_path, file_type, ocr_status) "
            "VALUES (?, ?, ?, ?, 'processing')",
            (session["user_id"], test_id, "", file_type),
        )

        save_path = student_dir / f"{sheet_id}.{ext}"
        f.save(str(save_path))
        execute(
            "UPDATE AnswerSheets SET file_path=? WHERE sheet_id=?",
            (str(save_path), sheet_id),
        )

        # Run the heavy pipeline (synchronous)
        try:
            _run_pipeline(sheet_id, str(save_path), questions)
            flash("Sheet processed successfully.", "success")
        except Exception as e:
            tb = traceback.format_exc()
            print(f"[pipeline] error on sheet {sheet_id}: {tb}")
            execute(
                "UPDATE AnswerSheets SET ocr_status='failed', ocr_error=? WHERE sheet_id=?",
                (str(e)[:500], sheet_id),
            )
            flash(f"Processing failed: {e}", "danger")

        return redirect(url_for("student.sheet_results", sheet_id=sheet_id))

    return render_template("student/upload_sheet.html", test=test, questions=questions)


# -------------------------------------------------------------------- #
# Pipeline                                                             #
# -------------------------------------------------------------------- #
def _run_pipeline(sheet_id: int, file_path: str, questions: list):
    """Full synchronous pipeline. Runs inside the request handler.

    Steps:
        1. OCR       -> raw text + confidence
        2. Cleanup   -> Flan-T5 fixes garble
        3. Segment   -> {q_num: answer_text}
        4. Grade     -> per-question scores via BERT
        5. Persist   -> ExtractedAnswers + Gradings
    """
    # Imports here so Flask app starts instantly even before models exist
    from nlp.ocr import ocr_sheet
    from nlp.llm_cleanup import clean_ocr_text, segment_by_question
    from nlp.grader import grade

    # ---- 1. OCR ----
    raw_text, avg_conf = ocr_sheet(file_path)
    execute(
        "UPDATE AnswerSheets SET raw_ocr_text=? WHERE sheet_id=?",
        (raw_text, sheet_id),
    )

    if avg_conf < Config.OCR_MIN_CONFIDENCE:
        execute(
            "UPDATE AnswerSheets SET ocr_status='failed', "
            "ocr_error=? WHERE sheet_id=?",
            (
                f"OCR confidence too low ({avg_conf:.2f}). "
                "Please re-upload a clearer scan (good lighting, dark ink, flat page).",
                sheet_id,
            ),
        )
        return

    # ---- 2. Cleanup ----
    cleaned = clean_ocr_text(raw_text)
    execute(
        "UPDATE AnswerSheets SET cleaned_text=? WHERE sheet_id=?",
        (cleaned, sheet_id),
    )

    # ---- 3. Segment ----
    segments = segment_by_question(cleaned, len(questions))

    # ---- 4 + 5. Grade and persist ----
    for idx, q in enumerate(questions, 1):
        student_ans = segments.get(idx, "").strip()
        ref_ans = q["reference_answer"] or ""

        extract_id = execute(
            "INSERT OR REPLACE INTO ExtractedAnswers "
            "(sheet_id, question_id, answer_text, confidence) "
            "VALUES (?, ?, ?, ?)",
            (sheet_id, q["question_id"], student_ans, None),
        )

        result = grade(student_ans, ref_ans, max_marks=float(q["max_marks"]))
        execute(
            "INSERT OR REPLACE INTO Gradings "
            "(extract_id, ai_score, final_score, similarity, rubric_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                extract_id,
                result["score"],
                result["score"],          # final == ai until teacher overrides
                result["similarity"],
                json.dumps({"model": result["model"]}),
            ),
        )

    execute(
        "UPDATE AnswerSheets SET ocr_status='done', ocr_error=NULL WHERE sheet_id=?",
        (sheet_id,),
    )


# -------------------------------------------------------------------- #
# Results                                                              #
# -------------------------------------------------------------------- #
@student_bp.route("/results/<int:sheet_id>")
@role_required("student")
def sheet_results(sheet_id: int):
    sheet = query_one(
        "SELECT s.*, t.test_name FROM AnswerSheets s "
        "JOIN Tests t ON t.test_id=s.test_id "
        "WHERE s.sheet_id=? AND s.student_id=?",
        (sheet_id, session["user_id"]),
    )
    if not sheet:
        flash("Sheet not found.", "danger")
        return redirect(url_for("student.home"))

    rows = query_all(
        "SELECT q.question_id, q.question_text, q.max_marks, "
        "       e.answer_text AS student_answer, "
        "       g.ai_score, g.final_score, g.similarity "
        "FROM Questions q "
        "LEFT JOIN ExtractedAnswers e ON e.question_id=q.question_id AND e.sheet_id=? "
        "LEFT JOIN Gradings g ON g.extract_id=e.extract_id "
        "WHERE q.test_id=? ORDER BY q.question_order",
        (sheet_id, sheet["test_id"]),
    )

    total = sum((r["final_score"] or 0) for r in rows)
    max_total = sum((r["max_marks"] or 0) for r in rows)

    return render_template(
        "student/sheet_results.html",
        sheet=sheet, rows=rows, total=total, max_total=max_total,
    )


@student_bp.route("/my-results")
@role_required("student")
def my_results():
    rows = query_all(
        "SELECT s.sheet_id, s.uploaded_at, s.ocr_status, t.test_name, "
        "       (SELECT SUM(COALESCE(g.final_score,g.ai_score,0)) "
        "        FROM ExtractedAnswers e "
        "        LEFT JOIN Gradings g ON g.extract_id=e.extract_id "
        "        WHERE e.sheet_id=s.sheet_id) AS total_score, "
        "       (SELECT SUM(q.max_marks) FROM Questions q WHERE q.test_id=s.test_id) AS max_total "
        "FROM AnswerSheets s JOIN Tests t ON t.test_id=s.test_id "
        "WHERE s.student_id=? ORDER BY s.sheet_id DESC",
        (session["user_id"],),
    )
    return render_template("student/my_results.html", rows=rows)