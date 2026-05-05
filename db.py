"""SQLite database helpers — no server needed.

The database is just a single file (`app.db` by default) stored in the
project root. SQLite is built into Python — no install required.

Usage from routes:
    from db import query_one, query_all, execute

    user = query_one("SELECT * FROM Users WHERE username=?", (uname,))
    rows = query_all("SELECT * FROM Tests WHERE created_by=?", (uid,))
    new_id = execute("INSERT INTO Tests (...) VALUES (...)", (...))
"""

import sqlite3
from pathlib import Path

from flask import g

from config import Config


def get_db() -> sqlite3.Connection:
    """Return a per-request connection. Reused within one request."""
    if "db" not in g:
        g.db = sqlite3.connect(
            Config.DATABASE_PATH,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        # Make rows behave like dicts (row["username"] instead of row[0])
        g.db.row_factory = sqlite3.Row
        # Enforce foreign keys (off by default in SQLite!)
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query_one(sql: str, params: tuple = ()):
    cur = get_db().execute(sql, params)
    row = cur.fetchone()
    cur.close()
    return dict(row) if row else None


def query_all(sql: str, params: tuple = ()):
    cur = get_db().execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    return [dict(r) for r in rows]


def execute(sql: str, params: tuple = ()) -> int:
    """Run INSERT/UPDATE/DELETE; returns lastrowid for INSERT."""
    db = get_db()
    cur = db.execute(sql, params)
    last_id = cur.lastrowid or 0
    db.commit()
    cur.close()
    return last_id


def execute_many(sql: str, seq_of_params):
    db = get_db()
    db.executemany(sql, seq_of_params)
    db.commit()


def init_app(app):
    """Wire close_db into Flask app teardown."""
    app.teardown_appcontext(close_db)
    # Make sure the DB schema exists on first run
    if not Path(Config.DATABASE_PATH).exists():
        init_schema()


def init_schema():
    """Create all tables from schema.sql if DB doesn't exist."""
    schema_file = Path(__file__).parent / "schema.sql"
    if not schema_file.exists():
        return
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.executescript(schema_file.read_text())
    conn.commit()
    conn.close()
    print(f"Database initialised at {Config.DATABASE_PATH}")