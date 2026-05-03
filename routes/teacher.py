"""Teacher routes — test creation + sheet review + score overrides.

URL prefix: /teacher
All routes require role='teacher'.
"""

import json
from datetime import datetime

from flask import (
    Blueprint, flash, redirect, render_template, request, send_file, session, url_for
)

from auth.decorators import role_required
from db import execute, query_all, query_one

teacher_bp = Blueprint("teacher", __name__)


# -------------------------------------------------------------------- #
# Dashboard                                                            #
# -------------------------------------------------------------------- #
@teacher_bp.route("/home")
@role_required("teacher")
def home():
    teacher_id = session["user_id"]
    tests = query_all(
        "SELECT t.test_id, t.test_name, t.created_at, "
        "       (SELECT COUNT(*) FROM Questions q WHERE q.test_id=t.test_id) AS qcount, "
        "       (SELECT COUNT(*) FROM AnswerSheets s WHERE s.test_id=t.test_id) AS scount "
        "FROM Tests t WHERE t.created_by=? ORDER BY t.test_id DESC",
        (teacher_id,),
    )
    return render_template("teacher/home.html", tests=tests)


# -------------------------------------------------------------------- #
# Test CRUD                                                            #
# -------------------------------------------------------------------- #
@teacher_bp.route("/test/new", methods=["GET", "POST"])
@role_required("teacher")
def test_new():
    if request.method == "POST":
        name = request.form["test_name"].strip()
        if not name:
            flash("Test name required.", "danger")
        else:
            tid = execute(
                "INSERT INTO Tests (test_name, created_by) VALUES (?, ?)",
                (name, session["user_id"]),
            )
            flash(f"Test '{name}' created. Now add questions.", "success")
            return redirect(url_for("teacher.test_manage", test_id=tid))
    return render_template("teacher/test_form.html")


@teacher_bp.route("/test/<int:test_id>/manage", methods=["GET", "POST"])
@role_required("teacher")
def test_manage(test_id: int):
    test = query_one(
        "SELECT * FROM Tests WHERE test_id=? AND created_by=?",
        (test_id, session["user_id"]),
    )
    if not test:
        flash("Test not found.", "danger")
        return redirect(url_for("teacher.home"))

    if request.method == "POST":
        q_text = request.form["question_text"].strip()
        ref_ans = request.form["reference_answer"].strip()
        max_marks = float(request.form.get("max_marks", 10) or 10)

        if not q_text or not ref_ans:
            flash("Question and reference answer are both required.", "danger")
        else:
            order = (query_one(
                "SELECT COALESCE(MAX(question_order),0)+1 AS n FROM Questions WHERE test_id=?",
                (test_id,),
            )["n"])
            qid = execute(
                "INSERT INTO Questions (test_id, question_text, max_marks, question_order) "
                "VALUES (?, ?, ?, ?)",
                (test_id, q_text, max_marks, order),
            )
            execute(
                "INSERT INTO ExpectedAnswers (question_id, answer_text) VALUES (?, ?)",
                (qid, ref_ans),
            )
            flash("Question added.", "success")
            return redirect(url_for("teacher.test_manage", test_id=test_id))

    questions = query_all(
        "SELECT q.question_id, q.question_text, q.max_marks, q.question_order, "
        "       (SELECT answer_text FROM ExpectedAnswers ea WHERE ea.question_id=q.question_id "
        "        ORDER BY ea.answer_id LIMIT 1) AS reference_answer "
        "FROM Questions q WHERE q.test_id=? ORDER BY q.question_order",
        (test_id,),
    )
    return render_template("teacher/test_manage.html", test=test, questions=questions)


@teacher_bp.route("/question/<int:qid>/delete", methods=["POST"])
@role_required("teacher")
def question_delete(qid: int):
    q = query_one(
        "SELECT q.test_id FROM Questions q "
        "JOIN Tests t ON t.test_id=q.test_id WHERE q.question_id=? AND t.created_by=?",
        (qid, session["user_id"]),
    )
    if not q:
        flash("Not allowed.", "danger")
        return redirect(url_for("teacher.home"))
    test_id = q["test_id"]
    execute("DELETE FROM Questions WHERE question_id=?", (qid,))
    flash("Question deleted.", "info")
    return redirect(url_for("teacher.test_manage", test_id=test_id))


# -------------------------------------------------------------------- #
# Sheet review                                                         #
# -------------------------------------------------------------------- #
@teacher_bp.route("/test/<int:test_id>/sheets")
@role_required("teacher")
def test_sheets(test_id: int):
    test = query_one(
        "SELECT * FROM Tests WHERE test_id=? AND created_by=?",
        (test_id, session["user_id"]),
    )
    if not test:
        flash("Test not found.", "danger")
        return redirect(url_for("teacher.home"))

    sheets = query_all(
        "SELECT s.sheet_id, s.uploaded_at, s.ocr_status, "
        "       u.username AS student_name, u.full_name "
        "FROM AnswerSheets s JOIN Users u ON u.user_id=s.student_id "
        "WHERE s.test_id=? ORDER BY s.sheet_id DESC",
        (test_id,),
    )
    return render_template("teacher/test_sheets.html", test=test, sheets=sheets)


@teacher_bp.route("/sheet/<int:sheet_id>")
@role_required("teacher")
def sheet_review(sheet_id: int):
    sheet = query_one(
        "SELECT s.*, u.username AS student_name, u.full_name, t.test_name, t.created_by "
        "FROM AnswerSheets s "
        "JOIN Users u ON u.user_id=s.student_id "
        "JOIN Tests t ON t.test_id=s.test_id "
        "WHERE s.sheet_id=?",
        (sheet_id,),
    )
    if not sheet or sheet["created_by"] != session["user_id"]:
        flash("Sheet not found or not yours.", "danger")
        return redirect(url_for("teacher.home"))

    rows = query_all(
        "SELECT q.question_id, q.question_text, q.max_marks, "
        "       (SELECT answer_text FROM ExpectedAnswers ea "
        "        WHERE ea.question_id=q.question_id ORDER BY ea.answer_id LIMIT 1) AS reference_answer, "
        "       e.extract_id, e.answer_text AS student_answer, "
        "       g.grade_id, g.ai_score, g.final_score, g.similarity, g.overridden_at "
        "FROM Questions q "
        "LEFT JOIN ExtractedAnswers e ON e.question_id=q.question_id AND e.sheet_id=? "
        "LEFT JOIN Gradings g ON g.extract_id=e.extract_id "
        "WHERE q.test_id=? ORDER BY q.question_order",
        (sheet_id, sheet["test_id"]),
    )
    return render_template("teacher/sheet_review.html", sheet=sheet, rows=rows)


@teacher_bp.route("/sheet/<int:sheet_id>/file")
@role_required("teacher")
def sheet_file(sheet_id: int):
    """Serve the original uploaded file so the teacher can see the handwriting."""
    sheet = query_one(
        "SELECT s.file_path, t.created_by FROM AnswerSheets s "
        "JOIN Tests t ON t.test_id=s.test_id WHERE s.sheet_id=?",
        (sheet_id,),
    )
    if not sheet or sheet["created_by"] != session["user_id"]:
        flash("Not allowed.", "danger")
        return redirect(url_for("teacher.home"))
    return send_file(sheet["file_path"])


@teacher_bp.route("/grading/<int:grade_id>/override", methods=["POST"])
@role_required("teacher")
def grading_override(grade_id: int):
    new_score = float(request.form["final_score"])
    sheet_id = int(request.form["sheet_id"])

    # Verify ownership
    own = query_one(
        "SELECT t.created_by FROM Gradings g "
        "JOIN ExtractedAnswers e ON e.extract_id=g.extract_id "
        "JOIN AnswerSheets s ON s.sheet_id=e.sheet_id "
        "JOIN Tests t ON t.test_id=s.test_id "
        "WHERE g.grade_id=?",
        (grade_id,),
    )
    if not own or own["created_by"] != session["user_id"]:
        flash("Not allowed.", "danger")
        return redirect(url_for("teacher.home"))

    execute(
        "UPDATE Gradings SET final_score=?, overridden_by=?, overridden_at=? WHERE grade_id=?",
        (new_score, session["user_id"], datetime.utcnow(), grade_id),
    )
    flash("Score overridden.", "success")
    return redirect(url_for("teacher.sheet_review", sheet_id=sheet_id))


# -------------------------------------------------------------------- #
# Aggregated scores                                                    #
# -------------------------------------------------------------------- #
@teacher_bp.route("/test/<int:test_id>/scores")
@role_required("teacher")
def test_scores(test_id: int):
    test = query_one(
        "SELECT * FROM Tests WHERE test_id=? AND created_by=?",
        (test_id, session["user_id"]),
    )
    if not test:
        flash("Test not found.", "danger")
        return redirect(url_for("teacher.home"))

    rows = query_all(
        "SELECT s.sheet_id, u.username AS student_name, s.uploaded_at, "
        "       SUM(COALESCE(g.final_score, g.ai_score, 0)) AS total_score, "
        "       SUM(q.max_marks) AS max_total "
        "FROM AnswerSheets s "
        "JOIN Users u ON u.user_id=s.student_id "
        "LEFT JOIN ExtractedAnswers e ON e.sheet_id=s.sheet_id "
        "LEFT JOIN Gradings g ON g.extract_id=e.extract_id "
        "LEFT JOIN Questions q ON q.question_id=e.question_id "
        "WHERE s.test_id=? "
        "GROUP BY s.sheet_id, u.username, s.uploaded_at "
        "ORDER BY total_score DESC",
        (test_id,),
    )
    return render_template("teacher/test_scores.html", test=test, rows=rows)