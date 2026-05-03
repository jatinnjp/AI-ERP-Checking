"""Single unified login / logout for ALL roles (admin, teacher, student)."""

from datetime import datetime

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash

from db import execute, query_one

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = query_one(
            "SELECT user_id, password, role, full_name "
            "FROM Users WHERE username=?",
            (username,),
        )

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["user_id"]
            session["role"] = user["role"]
            session["full_name"] = user["full_name"] or username

            execute(
                "UPDATE Users SET last_login=? WHERE user_id=?",
                (datetime.utcnow(), user["user_id"]),
            )

            target = {
                "admin": "admin.home",
                "teacher": "teacher.home",
                "student": "student.home",
            }[user["role"]]
            return redirect(url_for(target))

        flash("Invalid username or password.", "danger")

    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))