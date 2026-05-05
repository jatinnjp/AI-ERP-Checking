"""Seed sample users for demo / testing.

Run AFTER the app has been started at least once (so app.db exists),
OR run schema creation manually:
    sqlite3 app.db < schema.sql

Then:
    python seed.py

Creates:
    Username   | Password    | Role
    -----------+-------------+--------
    admin      | admin123    | admin
    teacher1   | teacher123  | teacher
    teacher2   | teacher123  | teacher
    student1   | student123  | student
    student2   | student123  | student
"""

import sqlite3

from werkzeug.security import generate_password_hash

from config import Config
from db import init_schema

USERS = [
    ("admin",    "admin123",   "admin",   "Admin User",  "admin@example.com"),
    ("teacher1", "teacher123", "teacher", "Ravi Sharma", "ravi@example.com"),
    ("teacher2", "teacher123", "teacher", "Sita Patel",  "sita@example.com"),
    ("student1", "student123", "student", "Rahul Singh", "rahul@example.com"),
    ("student2", "student123", "student", "Priya Verma", "priya@example.com"),
]


def main():
    # Make sure DB + tables exist
    init_schema()

    conn = sqlite3.connect(Config.DATABASE_PATH)
    cur = conn.cursor()

    for username, pw, role, full_name, email in USERS:
        try:
            cur.execute(
                "INSERT INTO Users (username, password, role, full_name, email) "
                "VALUES (?, ?, ?, ?, ?)",
                (username, generate_password_hash(pw), role, full_name, email),
            )
            print(f"  + created {role:8s}  {username:10s}  /  {pw}")
        except sqlite3.IntegrityError:
            print(f"  - {username:10s} already exists, skipping")

    conn.commit()
    cur.close()
    conn.close()

    print("\nDone. Use any of the above credentials to log in at /login.")


if __name__ == "__main__":
    main()