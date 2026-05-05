-- ====================================================================
-- AI Answer Sheet Evaluation System — SQLite schema
-- ====================================================================
-- This runs automatically on first app startup (see db.py init_schema).
-- You can also create it manually:
--     sqlite3 app.db < schema.sql
-- ====================================================================

PRAGMA foreign_keys = ON;

-- ---------- People (unified) ----------------------------------------
CREATE TABLE IF NOT EXISTS Users (
    user_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT UNIQUE NOT NULL,
    password    TEXT NOT NULL,                          -- werkzeug hash
    role        TEXT NOT NULL CHECK (role IN ('admin','teacher','student')),
    full_name   TEXT,
    email       TEXT UNIQUE,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_login  DATETIME
);

-- ---------- Tests ----------------------------------------------------
CREATE TABLE IF NOT EXISTS Tests (
    test_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    test_name   TEXT NOT NULL,
    created_by  INTEGER NOT NULL,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES Users(user_id)
);

CREATE TABLE IF NOT EXISTS Questions (
    question_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    test_id         INTEGER NOT NULL,
    question_text   TEXT NOT NULL,
    max_marks       REAL DEFAULT 10.0,
    question_order  INTEGER DEFAULT 0,
    FOREIGN KEY (test_id) REFERENCES Tests(test_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ExpectedAnswers (
    answer_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id  INTEGER NOT NULL,
    answer_text  TEXT NOT NULL,
    FOREIGN KEY (question_id) REFERENCES Questions(question_id) ON DELETE CASCADE
);

-- ---------- Uploaded answer sheet -----------------------------------
CREATE TABLE IF NOT EXISTS AnswerSheets (
    sheet_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id    INTEGER NOT NULL,
    test_id       INTEGER NOT NULL,
    file_path     TEXT NOT NULL,
    file_type     TEXT NOT NULL CHECK (file_type IN ('image','pdf')),
    page_count    INTEGER DEFAULT 1,
    uploaded_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    ocr_status    TEXT DEFAULT 'pending'
                  CHECK (ocr_status IN ('pending','processing','done','failed')),
    ocr_error     TEXT,
    raw_ocr_text  TEXT,
    cleaned_text  TEXT,
    FOREIGN KEY (student_id) REFERENCES Users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (test_id)    REFERENCES Tests(test_id) ON DELETE CASCADE
);

-- ---------- Per-question extracted text -----------------------------
CREATE TABLE IF NOT EXISTS ExtractedAnswers (
    extract_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    sheet_id     INTEGER NOT NULL,
    question_id  INTEGER NOT NULL,
    answer_text  TEXT,
    confidence   REAL,
    UNIQUE (sheet_id, question_id),
    FOREIGN KEY (sheet_id)    REFERENCES AnswerSheets(sheet_id) ON DELETE CASCADE,
    FOREIGN KEY (question_id) REFERENCES Questions(question_id)
);

-- ---------- AI grading + teacher overrides --------------------------
CREATE TABLE IF NOT EXISTS Gradings (
    grade_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    extract_id     INTEGER NOT NULL UNIQUE,
    ai_score       REAL,
    final_score    REAL,
    similarity     REAL,
    rubric_json    TEXT,
    graded_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    overridden_by  INTEGER,
    overridden_at  DATETIME,
    FOREIGN KEY (extract_id)    REFERENCES ExtractedAnswers(extract_id) ON DELETE CASCADE,
    FOREIGN KEY (overridden_by) REFERENCES Users(user_id)
);