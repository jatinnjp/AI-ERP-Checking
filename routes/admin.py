"""Admin routes — user management + system overview.

URL prefix: /admin (registered in app.py)
All routes require role='admin'.
"""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from auth.decorators import role_required
from db import execute, query_all, query_one

admin_bp = Blueprint("admin", __name__)


# -------------------------------------------------------------------- #
# Dashboard                                                            #
# -------------------------------------------------------------------- #
@admin_bp.route("/home")
@role_required("admin")
def home():
    counts = {
        "users":     query_one("SELECT COUNT(*) AS c FROM Users")["c"],
        "teachers":  query_one("SELECT COUNT(*) AS c FROM Users WHERE role='teacher'")["c"],
        "students":  query_one("SELECT COUNT(*) AS c FROM Users WHERE role='student'")["c"],
        "tests":     query_one("SELECT COUNT(*) AS c FROM Tests")["c"],
        "sheets":    query_one("SELECT COUNT(*) AS c FROM AnswerSheets")["c"],
    }
    return render_template("admin/home.html", counts=counts)


# -------------------------------------------------------------------- #
# User management                                                      #
# -------------------------------------------------------------------- #
@admin_bp.route("/users")
@role_required("admin")
def users():
    role_filter = request.args.get("role", "").strip()
    if role_filter in ("admin", "teacher", "student"):
        rows = query_all(
            "SELECT user_id, username, role, full_name, email, created_at, last_login "
            "FROM Users WHERE role=? ORDER BY user_id DESC",
            (role_filter,),
        )
    else:
        rows = query_all(
            "SELECT user_id, username, role, full_name, email, created_at, last_login "
            "FROM Users ORDER BY user_id DESC"
        )
    return render_template("admin/users.html", users=rows, role_filter=role_filter)


@admin_bp.route("/users/new", methods=["GET", "POST"])
@role_required("admin")
def user_new():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        role = request.form["role"]
        full_name = request.form.get("full_name", "").strip() or None
        email = request.form.get("email", "").strip() or None

        if role not in ("admin", "teacher", "student"):
            flash("Invalid role.", "danger")
            return redirect(url_for("admin.user_new"))

        try:
            execute(
                "INSERT INTO Users (username, password, role, full_name, email) "
                "VALUES (?, ?, ?, ?, ?)",
                (username, generate_password_hash(password), role, full_name, email),
            )
            flash(f"User '{username}' created.", "success")
            return redirect(url_for("admin.users"))
        except Exception as e:
            flash(f"Could not create user: {e}", "danger")

    return render_template("admin/user_form.html", user=None)


@admin_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@role_required("admin")
def user_edit(user_id: int):
    user = query_one("SELECT * FROM Users WHERE user_id=?", (user_id,))
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("admin.users"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip() or None
        email = request.form.get("email", "").strip() or None
        role = request.form.get("role", user["role"])
        new_pw = request.form.get("password", "")

        if new_pw:
            execute(
                "UPDATE Users SET full_name=?, email=?, role=?, password=? WHERE user_id=?",
                (full_name, email, role, generate_password_hash(new_pw), user_id),
            )
        else:
            execute(
                "UPDATE Users SET full_name=?, email=?, role=? WHERE user_id=?",
                (full_name, email, role, user_id),
            )
        flash("User updated.", "success")
        return redirect(url_for("admin.users"))

    return render_template("admin/user_form.html", user=user)


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@role_required("admin")
def user_delete(user_id: int):
    execute("DELETE FROM Users WHERE user_id=?", (user_id,))
    flash("User deleted.", "info")
    return redirect(url_for("admin.users"))


# -------------------------------------------------------------------- #
# System-wide views                                                    #
# -------------------------------------------------------------------- #
@admin_bp.route("/tests")
@role_required("admin")
def all_tests():
    rows = query_all(
        "SELECT t.test_id, t.test_name, t.created_at, u.username AS teacher_name, "
        "       (SELECT COUNT(*) FROM Questions q WHERE q.test_id=t.test_id) AS qcount, "
        "       (SELECT COUNT(*) FROM AnswerSheets s WHERE s.test_id=t.test_id) AS scount "
        "FROM Tests t JOIN Users u ON u.user_id=t.created_by "
        "ORDER BY t.test_id DESC"
    )
    return render_template("admin/all_tests.html", tests=rows)


@admin_bp.route("/sheets")
@role_required("admin")
def all_sheets():
    rows = query_all(
        "SELECT s.sheet_id, s.uploaded_at, s.ocr_status, "
        "       u.username AS student_name, t.test_name "
        "FROM AnswerSheets s "
        "JOIN Users u ON u.user_id=s.student_id "
        "JOIN Tests t ON t.test_id=s.test_id "
        "ORDER BY s.sheet_id DESC"
    )
    return render_template("admin/all_sheets.html", sheets=rows)