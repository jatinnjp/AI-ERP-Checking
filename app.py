"""AI Answer Sheet Evaluation System — Flask entry point.

Run:
    python app.py

Then open in your browser:
    http://127.0.0.1:5000/login
"""

from flask import Flask, redirect, url_for

from config import Config
import db


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialise SQLite (auto-creates app.db on first run)
    db.init_app(app)

    # Register blueprints (these files come in Parts 2 & 3)
    from auth.routes import auth_bp
    from routes.admin import admin_bp
    from routes.teacher import teacher_bp
    from routes.student import student_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp,   url_prefix="/admin")
    app.register_blueprint(teacher_bp, url_prefix="/teacher")
    app.register_blueprint(student_bp, url_prefix="/student")

    @app.route("/")
    def index():
        return redirect(url_for("auth.login"))

    @app.errorhandler(413)
    def too_large(_):
        return f"File too large. Max size: {Config.MAX_UPLOAD_MB} MB.", 413

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=Config.DEBUG)