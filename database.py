
import sqlite3
from pathlib import Path
from werkzeug.security import generate_password_hash

DATABASE_PATH = Path(__file__).parent / "edutrack.db"


def get_db_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def seed_default_data(connection):
    """Seed or safely update coordinator, faculty, and student user accounts with secure hashes.
    Never modifies or deletes existing academic records (students, marks, attendance, subjects)."""
    cursor = connection.cursor()

    # 1. Coordinator Account
    coord_pass = generate_password_hash("EduTrack@2026")
    coord_user = cursor.execute(
        "SELECT user_id FROM users WHERE username = ?", ("coordinator",)
    ).fetchone()
    if coord_user:
        cursor.execute(
            """
            UPDATE users
            SET password_hash = ?, role = 'coordinator'
            WHERE user_id = ?
            """,
            (coord_pass, coord_user["user_id"])
        )
    else:
        cursor.execute(
            """
            INSERT INTO users (username, password_hash, role)
            VALUES (?, ?, 'coordinator')
            """,
            ("coordinator", coord_pass)
        )

    # 2. Faculty Account
    fac_pass = generate_password_hash("Faculty@2026")
    fac_user = cursor.execute(
        "SELECT user_id FROM users WHERE username = ?", ("faculty",)
    ).fetchone()
    if fac_user:
        cursor.execute(
            """
            UPDATE users
            SET password_hash = ?, role = 'faculty'
            WHERE user_id = ?
            """,
            (fac_pass, fac_user["user_id"])
        )
        faculty_user_id = fac_user["user_id"]
    else:
        cursor.execute(
            """
            INSERT INTO users (username, password_hash, role)
            VALUES (?, ?, 'faculty')
            """,
            ("faculty", fac_pass)
        )
        faculty_user_id = cursor.lastrowid

    # Ensure faculty table has an entry for faculty_user_id
    fac_record = cursor.execute(
        "SELECT faculty_id FROM faculty WHERE user_id = ?", (faculty_user_id,)
    ).fetchone()
    if not fac_record:
        cursor.execute(
            """
            INSERT INTO faculty (user_id, full_name, department, email)
            VALUES (?, 'Faculty Member', 'CSE', 'faculty@edutrack.edu')
            """,
            (faculty_user_id,)
        )
        faculty_id = cursor.lastrowid
    else:
        faculty_id = fac_record["faculty_id"]

    # Ensure faculty has at least one assignment if subjects exist
    subject_row = cursor.execute("SELECT subject_id FROM subjects ORDER BY subject_id ASC LIMIT 1").fetchone()
    if subject_row:
        cursor.execute(
            """
            INSERT OR IGNORE INTO faculty_assignments (faculty_id, subject_id, year, section)
            VALUES (?, ?, 2, 'EK')
            """,
            (faculty_id, subject_row["subject_id"])
        )

    # 3. Student Account linked to an existing valid student record
    st_row = cursor.execute(
        "SELECT student_id, roll_number, full_name FROM students ORDER BY student_id ASC LIMIT 1"
    ).fetchone()
    if st_row:
        valid_student_id = st_row["student_id"]
        st_pass = generate_password_hash("Student@2026")
        st_user = cursor.execute(
            "SELECT user_id FROM users WHERE username = ?", ("student",)
        ).fetchone()
        if st_user:
            cursor.execute(
                """
                UPDATE users
                SET password_hash = ?, role = 'student', student_id = ?
                WHERE user_id = ?
                """,
                (st_pass, valid_student_id, st_user["user_id"])
            )
        else:
            cursor.execute(
                """
                INSERT INTO users (username, password_hash, role, student_id)
                VALUES (?, ?, 'student', ?)
                """,
                ("student", st_pass, valid_student_id)
            )

    connection.commit()


def init_db():
    connection = get_db_connection()

    connection.executescript("""
        CREATE TABLE IF NOT EXISTS students (
            student_id INTEGER PRIMARY KEY AUTOINCREMENT,
            roll_number TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            department TEXT NOT NULL,
            year INTEGER NOT NULL,
            section TEXT
        );

        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL
                CHECK (role IN ('coordinator', 'faculty', 'student')),
            student_id INTEGER,
            is_active INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (student_id)
                REFERENCES students(student_id)
        );

        CREATE TABLE IF NOT EXISTS subjects (
            subject_id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_code TEXT UNIQUE NOT NULL,
            subject_name TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS marks (
            mark_id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL,
            assessment_name TEXT NOT NULL,
            marks_obtained REAL NOT NULL,
            max_marks REAL NOT NULL,
            recorded_on TEXT DEFAULT CURRENT_DATE,
            FOREIGN KEY (student_id) REFERENCES students(student_id),
            FOREIGN KEY (subject_id) REFERENCES subjects(subject_id),
            CHECK (marks_obtained >= 0),
            CHECK (max_marks > 0),
            CHECK (marks_obtained <= max_marks)
        );

        CREATE TABLE IF NOT EXISTS attendance (
            attendance_id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL,
            total_classes INTEGER NOT NULL,
            attended_classes INTEGER NOT NULL,
            updated_on TEXT DEFAULT CURRENT_DATE,
            FOREIGN KEY (student_id) REFERENCES students(student_id),
            FOREIGN KEY (subject_id) REFERENCES subjects(subject_id),
            UNIQUE (student_id, subject_id),
            CHECK (total_classes >= 0),
            CHECK (attended_classes >= 0),
            CHECK (attended_classes <= total_classes)
        );

        CREATE TABLE IF NOT EXISTS faculty (
            faculty_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            department TEXT NOT NULL,
            email TEXT UNIQUE,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );

        CREATE TABLE IF NOT EXISTS faculty_assignments (
            assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            faculty_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL,
            year INTEGER NOT NULL,
            section TEXT NOT NULL,
            department TEXT,
            FOREIGN KEY (faculty_id)
                REFERENCES faculty(faculty_id),
            FOREIGN KEY (subject_id)
                REFERENCES subjects(subject_id),
            UNIQUE (faculty_id, subject_id, year, section)
        );

        CREATE TABLE IF NOT EXISTS class_advisor_assignments (
            assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            faculty_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            assigned_at TEXT DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (faculty_id) REFERENCES faculty(faculty_id),
            FOREIGN KEY (student_id) REFERENCES students(student_id),
            CHECK (is_active IN (0, 1))
        );
    """)

    # Column migrations for existing databases
    cols = [col[1] for col in connection.execute("PRAGMA table_info(users)").fetchall()]
    if "is_active" not in cols:
        connection.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")

    fa_cols = [col[1] for col in connection.execute("PRAGMA table_info(faculty_assignments)").fetchall()]
    if "department" not in fa_cols:
        connection.execute("ALTER TABLE faculty_assignments ADD COLUMN department TEXT")
        connection.execute("""
            UPDATE faculty_assignments
            SET department = (SELECT department FROM faculty WHERE faculty.faculty_id = faculty_assignments.faculty_id)
            WHERE department IS NULL
        """)

    # Partial unique index: each student has only one active class advisor
    connection.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_active_class_advisor
        ON class_advisor_assignments(student_id)
        WHERE is_active = 1
    """)

    # Index on faculty_id and is_active for advisor queries
    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_advisor_faculty
        ON class_advisor_assignments(faculty_id, is_active)
    """)

    seed_default_data(connection)
    connection.commit()
    connection.close()


if __name__ == "__main__":
    init_db()
    print("EduTrack database initialized and verified successfully!")
