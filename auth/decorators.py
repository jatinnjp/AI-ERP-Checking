"""Reusable auth decorators."""

from functools import wraps

from flask import flash, redirect, session, url_for


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return wrapper


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in first.", "warning")
                return redirect(url_for("auth.login"))
            if session.get("role") not in roles:
                flash("Access denied.", "danger")
                return redirect(url_for("auth.login"))
            return f(*args, **kwargs)
        return wrapper
    return decorator