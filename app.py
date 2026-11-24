
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db_connection, init_db

import json
import re
import urllib.request
import urllib.error


app = Flask(__name__)
app.secret_key = "edutrack_lite_secret_college_submission_key_2026"

# Initialize the SQLite database
init_db()


# --------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------

def calculate_risk(average_marks, attendance_percentage):
    """Calculate risk using the existing EduTrack Lite rules."""

    if average_marks is None or attendance_percentage is None:
        return "Insufficient Data"

    if average_marks < 40 or attendance_percentage < 65:
        return "High"

    if average_marks < 60 or attendance_percentage < 75:
        return "Medium"

    return "Low"


def get_current_user():
    """Retrieve currently authenticated user from session."""
    user_id = session.get("user_id")
    if not user_id:
        return None

    connection = get_db_connection()
    try:
        user = connection.execute(
            """
            SELECT user_id, username, role, student_id
            FROM users
            WHERE user_id = ?
            """,
            (user_id,)
        ).fetchone()

        if not user:
            return None

        user_dict = dict(user)

        if user["role"] == "faculty":
            fac = connection.execute(
                """
                SELECT faculty_id, full_name, department, email
                FROM faculty
                WHERE user_id = ?
                """,
                (user_id,)
            ).fetchone()

            if fac:
                user_dict["faculty_id"] = fac["faculty_id"]
                user_dict["full_name"] = fac["full_name"]
                user_dict["department"] = fac["department"]

        elif user["role"] == "student" and user["student_id"]:
            st = connection.execute(
                """
                SELECT student_id, full_name, roll_number, department, year, section
                FROM students
                WHERE student_id = ?
                """,
                (user["student_id"],)
            ).fetchone()

            if st:
                user_dict["student_id"] = st["student_id"]
                user_dict["full_name"] = st["full_name"]
                user_dict["roll_number"] = st["roll_number"]
                user_dict["department"] = st["department"]
                user_dict["year"] = st["year"]
                user_dict["section"] = st["section"]

        return user_dict
    finally:
        connection.close()


def generate_heuristic_ai_insights(student_data):
    """Generate structured academic insights when Ollama is offline or unavailable."""
    avg_marks = student_data.get("average_marks")
    att_pct = student_data.get("attendance_percentage")
    risk = student_data.get("risk_level", "Unknown")
    marks_list = student_data.get("marks", [])

    # 1. Risk Classification Explanation
    reasons = []
    if avg_marks is not None and avg_marks < 40:
        reasons.append(f"average marks ({avg_marks}%) are below 40%")
    elif avg_marks is not None and avg_marks < 60:
        reasons.append(f"average marks ({avg_marks}%) fall between 40% and 59%")
    elif avg_marks is not None:
        reasons.append(f"average marks ({avg_marks}%) meet or exceed the 60% mark threshold")

    if att_pct is not None and att_pct < 65:
        reasons.append(f"recorded attendance ({att_pct}%) is below 65%")
    elif att_pct is not None and att_pct < 75:
        reasons.append(f"recorded attendance ({att_pct}%) is below the 75% Low Risk threshold")
    elif att_pct is not None:
        reasons.append(f"recorded attendance ({att_pct}%) meets or exceeds the 75% Low Risk threshold")

    risk_explanation = (
        f"The student is classified under {risk} Risk according to EduTrack Lite criteria. "
        f"Recorded {', while '.join(reasons)}. Marks and attendance are evaluated as "
        "independent measurements contributing directly to this classification."
    )

    # 2. Visible Strengths
    strengths = []
    valid_marks = [m for m in marks_list if m.get("percentage") is not None]
    if valid_marks:
        best_subj = max(valid_marks, key=lambda x: x["percentage"])
        if best_subj["percentage"] >= 60:
            strengths.append(
                f"Strong recorded performance in {best_subj.get('subject_code', 'Subject')} "
                f"({best_subj.get('subject_name', '')}) with an assessment score of "
                f"{best_subj.get('marks_obtained')}/{best_subj.get('max_marks')} ({best_subj.get('percentage')}%)."
            )
    if att_pct is not None and att_pct >= 75:
        strengths.append(
            f"Attendance record stands at {att_pct}%, satisfying the application's Low Risk attendance threshold."
        )
    if not strengths:
        strengths.append("No specific high-scoring subject record is currently observed in available assessments.")
    visible_strengths = " ".join(strengths)

    # 3. Areas Needing Improvement
    improvements = []
    if valid_marks:
        lowest_subj = min(valid_marks, key=lambda x: x["percentage"])
        if lowest_subj["percentage"] < 50:
            improvements.append(
                f"Recorded score in {lowest_subj.get('subject_code', 'Subject')} is "
                f"{lowest_subj.get('marks_obtained')}/{lowest_subj.get('max_marks')} ({lowest_subj.get('percentage')}%), "
                "representing a measurable academic gap."
            )
    if att_pct is not None and att_pct < 75:
        improvements.append(
            f"Attendance percentage is recorded at {att_pct}%, which is below the application's 75% threshold."
        )
    if not improvements:
        improvements.append("No critical deficit is recorded across available academic assessments.")
    areas_needing_improvement = " ".join(improvements)

    # 4. Practical and Supportive Recommendations
    recommendations = [
        "1. Schedule targeted faculty review sessions focusing on challenging concepts identified in assessment records.",
        "2. Establish a consistent weekly study routine to systematically improve upcoming assessment readiness.",
        "3. Monitor class attendance weekly to steadily progress toward the 75% Low Risk attendance threshold."
    ]
    recs_text = "\n".join(recommendations)

    return f"""1. Risk Classification Explanation
{risk_explanation}

2. Visible Strengths
{visible_strengths}

3. Areas Needing Improvement
{areas_needing_improvement}

4. Practical and Supportive Recommendations
{recs_text}"""


def get_student_analysis_data(student_id):
    """Retrieve a student's complete academic analysis."""

    connection = get_db_connection()

    try:
        student = connection.execute(
            """
            SELECT student_id, roll_number, full_name,
                   department, year, section
            FROM students
            WHERE student_id = ?
            """,
            (student_id,)
        ).fetchone()

        if student is None:
            return None

        marks = connection.execute(
            """
            SELECT
                subjects.subject_code,
                subjects.subject_name,
                marks.assessment_name,
                marks.marks_obtained,
                marks.max_marks,
                ROUND(
                    100.0 * marks.marks_obtained /
                    NULLIF(marks.max_marks, 0), 2
                ) AS percentage
            FROM marks
            JOIN subjects
                ON marks.subject_id = subjects.subject_id
            WHERE marks.student_id = ?
            ORDER BY marks.mark_id ASC
            """,
            (student_id,)
        ).fetchall()

        attendance = connection.execute(
            """
            SELECT
                subjects.subject_code,
                subjects.subject_name,
                attendance.total_classes,
                attendance.attended_classes,
                ROUND(
                    100.0 * attendance.attended_classes /
                    NULLIF(attendance.total_classes, 0), 2
                ) AS percentage
            FROM attendance
            JOIN subjects
                ON attendance.subject_id = subjects.subject_id
            WHERE attendance.student_id = ?
            ORDER BY attendance.attendance_id ASC
            """,
            (student_id,)
        ).fetchall()

        total_obtained = sum(
            record["marks_obtained"] for record in marks
        )

        total_maximum = sum(
            record["max_marks"] for record in marks
        )

        total_attended = sum(
            record["attended_classes"] for record in attendance
        )

        total_classes = sum(
            record["total_classes"] for record in attendance
        )

        average_marks = (
            round(100 * total_obtained / total_maximum, 2)
            if total_maximum > 0 else None
        )

        attendance_percentage = (
            round(100 * total_attended / total_classes, 2)
            if total_classes > 0 else None
        )

        risk = calculate_risk(
            average_marks,
            attendance_percentage
        )

        return {
            "student": dict(student),
            "average_marks": average_marks,
            "attendance_percentage": attendance_percentage,
            "risk_level": risk,
            "marks": [dict(record) for record in marks],
            "attendance": [dict(record) for record in attendance]
        }

    finally:
        connection.close()


# --------------------------------------------------
# AUTHENTICATION & PORTAL ACCESS
# --------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "GET":
        current_user = get_current_user()
        if current_user:
            if current_user["role"] == "faculty":
                return redirect(url_for("faculty_dashboard"))
            elif current_user["role"] == "student":
                return redirect(url_for("student_dashboard"))
            elif current_user["role"] == "coordinator":
                return redirect(url_for("home"))

    if request.method == "POST":
        data = request.form if request.form else (request.get_json(silent=True) or {})
        username = str(data.get("username", "")).strip()
        password = str(data.get("password", "")).strip()

        if not username or not password:
            error_msg = "Please enter both username and password."
            if request.is_json:
                return jsonify({"error": error_msg}), 400
            return render_template("login.html", error=error_msg)

        connection = get_db_connection()
        try:
            user = connection.execute(
                """
                SELECT user_id, username, password_hash, role, student_id, is_active
                FROM users
                WHERE username = ?
                """,
                (username,)
            ).fetchone()

            if not user or not check_password_hash(user["password_hash"], password):
                error_msg = "Invalid username or password."
                if request.is_json:
                    return jsonify({"error": error_msg}), 401
                return render_template("login.html", error=error_msg)

            if user["is_active"] == 0:
                error_msg = "Your account has been deactivated. Please contact the coordinator."
                if request.is_json:
                    return jsonify({"error": error_msg}), 403
                return render_template("login.html", error=error_msg)

            session["user_id"] = user["user_id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            session["student_id"] = user["student_id"]

            faculty_id = None
            if user["role"] == "faculty":
                faculty = connection.execute(
                    "SELECT faculty_id FROM faculty WHERE user_id = ?",
                    (user["user_id"],)
                ).fetchone()
                if faculty:
                    faculty_id = faculty["faculty_id"]
                    session["faculty_id"] = faculty_id

            if request.is_json:
                redirect_url = url_for("home")
                if user["role"] == "faculty":
                    redirect_url = url_for("faculty_dashboard")
                elif user["role"] == "student":
                    redirect_url = url_for("student_dashboard")

                return jsonify({
                    "message": "Login successful",
                    "redirect_url": redirect_url,
                    "user": {
                        "user_id": user["user_id"],
                        "username": user["username"],
                        "role": user["role"],
                        "faculty_id": faculty_id,
                        "student_id": user["student_id"]
                    }
                }), 200

            if user["role"] == "faculty":
                return redirect(url_for("faculty_dashboard"))
            elif user["role"] == "student" and user["student_id"]:
                return redirect(url_for("student_dashboard"))
            return redirect(url_for("home"))

        finally:
            connection.close()

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


@app.route("/api/auth/me", methods=["GET"])
def api_auth_me():
    user = get_current_user()
    if not user:
        return jsonify({"authenticated": False}), 200
    return jsonify({"authenticated": True, "user": user}), 200


@app.route("/api/auth/login", methods=["POST"])
def api_auth_login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", "")).strip()

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    connection = get_db_connection()
    try:
        user = connection.execute(
            """
            SELECT user_id, username, password_hash, role, student_id, is_active
            FROM users
            WHERE username = ?
            """,
            (username,)
        ).fetchone()

        if not user or not check_password_hash(user["password_hash"], password):
            return jsonify({"error": "Invalid username or password"}), 401

        if user["is_active"] == 0:
            return jsonify({"error": "Your account has been deactivated. Please contact the coordinator."}), 403

        session["user_id"] = user["user_id"]
        session["username"] = user["username"]
        session["role"] = user["role"]
        session["student_id"] = user["student_id"]

        faculty_id = None
        full_name = user["username"]
        if user["role"] == "faculty":
            faculty = connection.execute(
                "SELECT faculty_id, full_name FROM faculty WHERE user_id = ?",
                (user["user_id"],)
            ).fetchone()
            if faculty:
                faculty_id = faculty["faculty_id"]
                full_name = faculty["full_name"]
                session["faculty_id"] = faculty_id

        redirect_url = url_for("home")
        if user["role"] == "faculty":
            redirect_url = url_for("faculty_dashboard")
        elif user["role"] == "student":
            redirect_url = url_for("student_dashboard")

        return jsonify({
            "message": "Login successful",
            "redirect_url": redirect_url,
            "user": {
                "user_id": user["user_id"],
                "username": user["username"],
                "full_name": full_name,
                "role": user["role"],
                "faculty_id": faculty_id,
                "student_id": user["student_id"]
            }
        }), 200
    finally:
        connection.close()


@app.route("/api/auth/logout", methods=["POST"])
def api_auth_logout():
    session.clear()
    return jsonify({"message": "Logged out successfully"}), 200


# --------------------------------------------------
# HOME PAGE (COORDINATOR DASHBOARD)
# --------------------------------------------------

@app.route("/")
def home():
    user = get_current_user()
    if not user:
        return redirect(url_for("login_page"))
    if user["role"] == "student":
        return redirect(url_for("student_dashboard"))
    if user["role"] == "faculty":
        return redirect(url_for("faculty_dashboard"))
    return render_template("index.html", user=user)


# --------------------------------------------------
# STUDENT MANAGEMENT
# --------------------------------------------------

@app.route("/api/students", methods=["POST"])
def add_student():
    if session.get("role") == "student":
        return jsonify({"error": "Access denied. Action prohibited for student accounts."}), 403

    data = request.get_json(silent=True) or {}

    roll_number = str(data.get("roll_number", "")).strip()
    full_name = str(data.get("full_name", "")).strip()
    department = str(data.get("department", "")).strip()
    year = data.get("year")
    section = str(data.get("section", "")).strip()

    if not all([roll_number, full_name, department, year]):
        return jsonify({
            "error": "Please fill all required fields"
        }), 400

    try:
        year = int(year)

        if year < 1 or year > 6:
            return jsonify({
                "error": "Invalid academic year"
            }), 400

    except (ValueError, TypeError):
        return jsonify({
            "error": "Year must be a number"
        }), 400

    connection = get_db_connection()

    try:
        connection.execute(
            """
            INSERT INTO students
            (roll_number, full_name, department, year, section)
            VALUES (?, ?, ?, ?, ?)
            """,
            (roll_number, full_name, department, year, section)
        )

        connection.commit()

        return jsonify({
            "message": "Student added successfully"
        }), 201

    except Exception as error:

        if "UNIQUE constraint failed" in str(error):
            return jsonify({
                "error": "Roll number already exists"
            }), 409

        return jsonify({
            "error": "Unable to save student"
        }), 500

    finally:
        connection.close()


@app.route("/api/students", methods=["GET"])
def get_students():
    if session.get("role") == "student":
        return jsonify({"error": "Access denied. Students cannot access student directory."}), 403

    connection = get_db_connection()

    try:
        students = connection.execute(
            """
            SELECT *
            FROM students
            ORDER BY student_id ASC
            """
        ).fetchall()

        return jsonify([
            dict(student) for student in students
        ])

    finally:
        connection.close()


@app.route("/api/students/<int:student_id>/dependencies", methods=["GET"])
def get_student_dependencies(student_id):

    connection = get_db_connection()

    try:
        student = connection.execute(
            "SELECT student_id, roll_number, full_name FROM students WHERE student_id = ?",
            (student_id,)
        ).fetchone()

        if not student:
            return jsonify({
                "error": "Student not found"
            }), 404

        marks_count = connection.execute(
            "SELECT COUNT(*) FROM marks WHERE student_id = ?",
            (student_id,)
        ).fetchone()[0]

        attendance_count = connection.execute(
            "SELECT COUNT(*) FROM attendance WHERE student_id = ?",
            (student_id,)
        ).fetchone()[0]

        users_count = connection.execute(
            "SELECT COUNT(*) FROM users WHERE student_id = ?",
            (student_id,)
        ).fetchone()[0]

        can_delete = (marks_count == 0 and attendance_count == 0 and users_count == 0)

        return jsonify({
            "student_id": student["student_id"],
            "roll_number": student["roll_number"],
            "full_name": student["full_name"],
            "marks_count": marks_count,
            "attendance_count": attendance_count,
            "users_count": users_count,
            "can_delete": can_delete
        }), 200

    finally:
        connection.close()


@app.route("/api/students/<int:student_id>", methods=["PUT"])
def update_student(student_id):
    if session.get("role") == "student":
        return jsonify({"error": "Access denied. Action prohibited for student accounts."}), 403

    data = request.get_json(silent=True) or {}

    roll_number = str(data.get("roll_number", "")).strip()
    full_name = str(data.get("full_name", "")).strip()
    department = str(data.get("department", "")).strip()
    year = data.get("year")
    section = str(data.get("section", "")).strip()

    if not all([roll_number, full_name, department, year]):
        return jsonify({
            "error": "Please fill all required fields"
        }), 400

    try:
        year = int(year)

        if year < 1 or year > 6:
            return jsonify({
                "error": "Invalid academic year"
            }), 400

    except (ValueError, TypeError):
        return jsonify({
            "error": "Year must be a number"
        }), 400

    connection = get_db_connection()

    try:
        existing = connection.execute(
            "SELECT student_id FROM students WHERE student_id = ?",
            (student_id,)
        ).fetchone()

        if not existing:
            return jsonify({
                "error": "Student not found"
            }), 404

        duplicate = connection.execute(
            "SELECT student_id FROM students WHERE roll_number = ? AND student_id != ?",
            (roll_number, student_id)
        ).fetchone()

        if duplicate:
            return jsonify({
                "error": "Roll number already exists"
            }), 409

        connection.execute(
            """
            UPDATE students
            SET roll_number = ?,
                full_name = ?,
                department = ?,
                year = ?,
                section = ?
            WHERE student_id = ?
            """,
            (roll_number, full_name, department, year, section, student_id)
        )

        connection.commit()

        return jsonify({
            "message": "Student updated successfully"
        }), 200

    except Exception as error:

        if "UNIQUE constraint failed" in str(error):
            return jsonify({
                "error": "Roll number already exists"
            }), 409

        return jsonify({
            "error": "Unable to update student"
        }), 500

    finally:
        connection.close()


@app.route("/api/students/<int:student_id>", methods=["DELETE"])
def delete_student(student_id):
    if session.get("role") == "student":
        return jsonify({"error": "Access denied. Action prohibited for student accounts."}), 403

    connection = get_db_connection()

    try:
        existing = connection.execute(
            "SELECT student_id, roll_number, full_name FROM students WHERE student_id = ?",
            (student_id,)
        ).fetchone()

        if not existing:
            return jsonify({
                "error": "Student not found"
            }), 404

        marks_count = connection.execute(
            "SELECT COUNT(*) FROM marks WHERE student_id = ?",
            (student_id,)
        ).fetchone()[0]

        attendance_count = connection.execute(
            "SELECT COUNT(*) FROM attendance WHERE student_id = ?",
            (student_id,)
        ).fetchone()[0]

        users_count = connection.execute(
            "SELECT COUNT(*) FROM users WHERE student_id = ?",
            (student_id,)
        ).fetchone()[0]

        if marks_count > 0 or attendance_count > 0 or users_count > 0:
            reasons = []
            if marks_count > 0:
                reasons.append(f"{marks_count} marks record(s)")
            if attendance_count > 0:
                reasons.append(f"{attendance_count} attendance record(s)")
            if users_count > 0:
                reasons.append(f"{users_count} user account(s)")
            reasons_str = ", ".join(reasons)

            return jsonify({
                "error": f"Cannot delete student: linked {reasons_str} exist. Deletion is blocked under strict academic protection."
            }), 409

        connection.execute(
            "DELETE FROM students WHERE student_id = ?",
            (student_id,)
        )

        connection.commit()

        return jsonify({
            "message": "Student deleted successfully"
        }), 200

    except Exception:
        return jsonify({
            "error": "Unable to delete student"
        }), 500

    finally:
        connection.close()


# --------------------------------------------------
# STUDENT ACCOUNT MANAGEMENT API (COORDINATOR ONLY)
# --------------------------------------------------

@app.route("/api/student-accounts", methods=["GET"])
def get_student_accounts():
    """List all students with their portal login accounts and status."""
    if session.get("role") != "coordinator":
        return jsonify({"error": "Access denied. Coordinator authorization required."}), 403

    search_query = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "").strip().lower()

    connection = get_db_connection()
    try:
        base_query = """
            SELECT
                s.student_id,
                s.roll_number,
                s.full_name,
                s.department,
                s.year,
                s.section,
                u.user_id,
                u.username,
                COALESCE(u.is_active, 1) AS is_active,
                CASE WHEN u.user_id IS NOT NULL THEN 1 ELSE 0 END AS has_account
            FROM students s
            LEFT JOIN (
                SELECT user_id, username, student_id, is_active
                FROM (
                    SELECT user_id, username, student_id, is_active
                    FROM users
                    WHERE role = 'student'
                    ORDER BY user_id DESC
                )
                GROUP BY student_id
            ) u ON s.student_id = u.student_id
            WHERE 1=1
        """
        params = []

        if search_query:
            base_query += """ AND (
                s.full_name LIKE ? OR
                s.roll_number LIKE ? OR
                u.username LIKE ?
            )"""
            wildcard = f"%{search_query}%"
            params.extend([wildcard, wildcard, wildcard])

        if status_filter == "active":
            base_query += " AND u.user_id IS NOT NULL AND u.is_active = 1"
        elif status_filter == "inactive":
            base_query += " AND u.user_id IS NOT NULL AND u.is_active = 0"
        elif status_filter == "unassigned":
            base_query += " AND u.user_id IS NULL"

        base_query += " ORDER BY s.roll_number ASC"

        rows = connection.execute(base_query, params).fetchall()
        return jsonify([dict(row) for row in rows]), 200
    finally:
        connection.close()


@app.route("/api/students-without-accounts", methods=["GET"])
def get_students_without_accounts():
    """List existing students who do not yet have a login account."""
    if session.get("role") != "coordinator":
        return jsonify({"error": "Access denied. Coordinator authorization required."}), 403

    connection = get_db_connection()
    try:
        rows = connection.execute("""
            SELECT student_id, roll_number, full_name, department, year, section
            FROM students
            WHERE student_id NOT IN (
                SELECT student_id FROM users WHERE student_id IS NOT NULL AND role = 'student'
            )
            ORDER BY roll_number ASC
        """).fetchall()
        return jsonify([dict(row) for row in rows]), 200
    finally:
        connection.close()


@app.route("/api/student-accounts", methods=["POST"])
def create_student_account():
    """Create a portal login account for an existing student record."""
    if session.get("role") != "coordinator":
        return jsonify({"error": "Access denied. Coordinator authorization required."}), 403

    data = request.get_json(silent=True) or {}
    student_id = data.get("student_id")
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", "")).strip()

    if not student_id or not username or not password:
        return jsonify({"error": "Student ID, username, and password are required."}), 400

    try:
        student_id = int(student_id)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid student ID."}), 400

    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters long."}), 400

    connection = get_db_connection()
    try:
        # 1. Identify existing student
        student = connection.execute(
            "SELECT student_id, roll_number, full_name, department, year, section FROM students WHERE student_id = ?",
            (student_id,)
        ).fetchone()

        if not student:
            return jsonify({"error": "Student record not found."}), 404

        # 2. Check if student already has a login account
        existing_account = connection.execute(
            "SELECT user_id, username FROM users WHERE student_id = ? AND role = 'student'",
            (student_id,)
        ).fetchone()

        if existing_account:
            return jsonify({
                "error": f"Student '{student['full_name']}' already has a portal login account ({existing_account['username']})."
            }), 409

        # 3. Check if username is already taken
        username_taken = connection.execute(
            "SELECT user_id FROM users WHERE username = ?",
            (username,)
        ).fetchone()

        if username_taken:
            return jsonify({"error": f"Username '{username}' is already taken. Please choose another username."}), 409

        # 4. Hash password and insert user account in transaction
        pass_hash = generate_password_hash(password)
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO users (username, password_hash, role, student_id, is_active)
            VALUES (?, ?, 'student', ?, 1)
            """,
            (username, pass_hash, student_id)
        )
        new_user_id = cursor.lastrowid
        connection.commit()

        return jsonify({
            "message": f"Login account for '{student['full_name']}' ({username}) created successfully.",
            "user_id": new_user_id,
            "student_id": student_id,
            "username": username
        }), 201

    except Exception as error:
        connection.rollback()
        return jsonify({"error": f"Unable to create student login account: {str(error)}"}), 500
    finally:
        connection.close()


@app.route("/api/student-accounts/<int:user_id>/reset-password", methods=["POST"])
def reset_student_password(user_id):
    """Reset the password for an existing student login account."""
    if session.get("role") != "coordinator":
        return jsonify({"error": "Access denied. Coordinator authorization required."}), 403

    data = request.get_json(silent=True) or {}
    new_password = str(data.get("new_password", "")).strip()

    if not new_password or len(new_password) < 6:
        return jsonify({"error": "New password must be at least 6 characters long."}), 400

    connection = get_db_connection()
    try:
        user = connection.execute(
            "SELECT user_id, username, role FROM users WHERE user_id = ? AND role = 'student'",
            (user_id,)
        ).fetchone()

        if not user:
            return jsonify({"error": "Student account not found."}), 404

        pass_hash = generate_password_hash(new_password)
        connection.execute(
            "UPDATE users SET password_hash = ? WHERE user_id = ?",
            (pass_hash, user_id)
        )
        connection.commit()

        return jsonify({"message": f"Password for student '{user['username']}' reset successfully."}), 200
    finally:
        connection.close()


@app.route("/api/student-accounts/<int:user_id>/status", methods=["PATCH", "POST"])
def toggle_student_account_status(user_id):
    """Activate or deactivate a student login account."""
    if session.get("role") != "coordinator":
        return jsonify({"error": "Access denied. Coordinator authorization required."}), 403

    connection = get_db_connection()
    try:
        user = connection.execute(
            "SELECT user_id, username, is_active FROM users WHERE user_id = ? AND role = 'student'",
            (user_id,)
        ).fetchone()

        if not user:
            return jsonify({"error": "Student account not found."}), 404

        data = request.get_json(silent=True) or {}
        if "is_active" in data:
            new_status = 1 if data["is_active"] else 0
        else:
            new_status = 0 if user["is_active"] == 1 else 1

        connection.execute(
            "UPDATE users SET is_active = ? WHERE user_id = ?",
            (new_status, user_id)
        )
        connection.commit()

        status_text = "activated" if new_status == 1 else "deactivated"
        return jsonify({
            "message": f"Account for '{user['username']}' {status_text} successfully.",
            "is_active": new_status
        }), 200
    finally:
        connection.close()


@app.route("/api/student-accounts/<int:user_id>", methods=["DELETE"])
def delete_student_account(user_id):
    """Delete a student login account while strictly preserving academic student profile."""
    if session.get("role") != "coordinator":
        return jsonify({"error": "Access denied. Coordinator authorization required."}), 403

    connection = get_db_connection()
    try:
        user = connection.execute(
            "SELECT user_id, username, student_id FROM users WHERE user_id = ? AND role = 'student'",
            (user_id,)
        ).fetchone()

        if not user:
            return jsonify({"error": "Student account not found."}), 404

        connection.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        connection.commit()

        return jsonify({
            "message": f"Login account for '{user['username']}' removed successfully. Student academic records remain preserved."
        }), 200
    finally:
        connection.close()


# --------------------------------------------------
# SUBJECT MANAGEMENT
# --------------------------------------------------

@app.route("/api/subjects", methods=["POST"])
def add_subject():
    if session.get("role") != "coordinator":
        return jsonify({"error": "Unauthorized. Coordinator access required."}), 403

    data = request.get_json(silent=True) or {}

    subject_code = str(data.get("subject_code", "")).strip()
    subject_name = str(data.get("subject_name", "")).strip()

    if not subject_code or not subject_name:
        return jsonify({
            "error": "Please fill all required fields"
        }), 400

    connection = get_db_connection()

    try:
        connection.execute(
            """
            INSERT INTO subjects (subject_code, subject_name)
            VALUES (?, ?)
            """,
            (subject_code, subject_name)
        )

        connection.commit()

        return jsonify({
            "message": "Subject added successfully"
        }), 201

    except Exception as error:

        if "UNIQUE constraint failed" in str(error):
            return jsonify({
                "error": "Subject code already exists"
            }), 409

        return jsonify({
            "error": "Unable to save subject"
        }), 500

    finally:
        connection.close()


@app.route("/api/subjects", methods=["GET"])
def get_subjects():

    connection = get_db_connection()

    try:
        subjects = connection.execute(
            """
            SELECT *
            FROM subjects
            ORDER BY subject_id ASC
            """
        ).fetchall()

        return jsonify([
            dict(subject) for subject in subjects
        ])

    finally:
        connection.close()


@app.route("/api/subjects/<int:subject_id>/dependencies", methods=["GET"])
def get_subject_dependencies(subject_id):

    connection = get_db_connection()

    try:
        subject = connection.execute(
            "SELECT subject_id, subject_code, subject_name FROM subjects WHERE subject_id = ?",
            (subject_id,)
        ).fetchone()

        if not subject:
            return jsonify({"error": "Subject not found"}), 404

        marks_count = connection.execute(
            "SELECT COUNT(*) FROM marks WHERE subject_id = ?",
            (subject_id,)
        ).fetchone()[0]

        attendance_count = connection.execute(
            "SELECT COUNT(*) FROM attendance WHERE subject_id = ?",
            (subject_id,)
        ).fetchone()[0]

        assignments_count = connection.execute(
            "SELECT COUNT(*) FROM faculty_assignments WHERE subject_id = ?",
            (subject_id,)
        ).fetchone()[0]

        can_delete = (marks_count == 0 and attendance_count == 0 and assignments_count == 0)

        return jsonify({
            "subject_id": subject["subject_id"],
            "subject_code": subject["subject_code"],
            "subject_name": subject["subject_name"],
            "marks_count": marks_count,
            "attendance_count": attendance_count,
            "assignments_count": assignments_count,
            "can_delete": can_delete
        }), 200

    finally:
        connection.close()


@app.route("/api/subjects/<int:subject_id>", methods=["PUT"])
def update_subject(subject_id):
    if session.get("role") == "student":
        return jsonify({"error": "Access denied. Action prohibited for student accounts."}), 403

    data = request.get_json(silent=True) or {}

    subject_code = str(data.get("subject_code", "")).strip()
    subject_name = str(data.get("subject_name", "")).strip()

    if not subject_code or not subject_name:
        return jsonify({"error": "Subject code and subject name are required"}), 400

    connection = get_db_connection()

    try:
        existing = connection.execute(
            "SELECT subject_id FROM subjects WHERE subject_id = ?",
            (subject_id,)
        ).fetchone()

        if not existing:
            return jsonify({"error": "Subject not found"}), 404

        duplicate = connection.execute(
            "SELECT subject_id FROM subjects WHERE subject_code = ? AND subject_id != ?",
            (subject_code, subject_id)
        ).fetchone()

        if duplicate:
            return jsonify({"error": "Subject code already exists"}), 409

        connection.execute(
            """
            UPDATE subjects
            SET subject_code = ?,
                subject_name = ?
            WHERE subject_id = ?
            """,
            (subject_code, subject_name, subject_id)
        )

        connection.commit()

        return jsonify({"message": "Subject updated successfully"}), 200

    except Exception as error:
        if "UNIQUE constraint failed" in str(error):
            return jsonify({"error": "Subject code already exists"}), 409
        return jsonify({"error": "Unable to update subject"}), 500

    finally:
        connection.close()


@app.route("/api/subjects/<int:subject_id>", methods=["DELETE"])
def delete_subject(subject_id):
    if session.get("role") == "student":
        return jsonify({"error": "Access denied. Action prohibited for student accounts."}), 403

    connection = get_db_connection()

    try:
        existing = connection.execute(
            "SELECT subject_id, subject_code, subject_name FROM subjects WHERE subject_id = ?",
            (subject_id,)
        ).fetchone()

        if not existing:
            return jsonify({"error": "Subject not found"}), 404

        marks_count = connection.execute(
            "SELECT COUNT(*) FROM marks WHERE subject_id = ?",
            (subject_id,)
        ).fetchone()[0]

        attendance_count = connection.execute(
            "SELECT COUNT(*) FROM attendance WHERE subject_id = ?",
            (subject_id,)
        ).fetchone()[0]

        assignments_count = connection.execute(
            "SELECT COUNT(*) FROM faculty_assignments WHERE subject_id = ?",
            (subject_id,)
        ).fetchone()[0]

        if marks_count > 0 or attendance_count > 0 or assignments_count > 0:
            reasons = []
            if marks_count > 0:
                reasons.append(f"{marks_count} mark score(s)")
            if attendance_count > 0:
                reasons.append(f"{attendance_count} attendance record(s)")
            if assignments_count > 0:
                reasons.append(f"{assignments_count} faculty assignment(s)")

            return jsonify({
                "error": f"Cannot delete subject: linked {', '.join(reasons)} exist. Deletion is blocked under strict academic protection."
            }), 409

        connection.execute(
            "DELETE FROM subjects WHERE subject_id = ?",
            (subject_id,)
        )

        connection.commit()

        return jsonify({"message": "Subject deleted successfully"}), 200

    except Exception:
        return jsonify({"error": "Unable to delete subject"}), 500

    finally:
        connection.close()


# --------------------------------------------------
# MARKS MANAGEMENT
# --------------------------------------------------

@app.route("/api/marks", methods=["POST"])
def add_marks():
    if session.get("role") == "student":
        return jsonify({"error": "Access denied. Action prohibited for student accounts."}), 403

    data = request.get_json(silent=True) or {}

    try:
        student_id = int(data.get("student_id"))
        subject_id = int(data.get("subject_id"))

        assessment_name = str(
            data.get("assessment_name", "")
        ).strip()

        marks_obtained = float(data.get("marks_obtained"))
        max_marks = float(data.get("max_marks"))

        if not assessment_name:
            return jsonify({
                "error": "Assessment name is required"
            }), 400

        if marks_obtained < 0 or max_marks <= 0:
            return jsonify({
                "error": "Invalid marks"
            }), 400

        if marks_obtained > max_marks:
            return jsonify({
                "error": "Marks cannot exceed maximum marks"
            }), 400

    except (ValueError, TypeError):
        return jsonify({
            "error": "Please enter valid marks and selections"
        }), 400

    connection = get_db_connection()

    try:
        if session.get("role") == "faculty":
            fac_id = session.get("faculty_id")
            st = connection.execute(
                "SELECT year, section, department FROM students WHERE student_id = ?",
                (student_id,)
            ).fetchone()
            if not st:
                return jsonify({"error": "Student not found"}), 404
            has_assign = connection.execute(
                """
                SELECT assignment_id FROM faculty_assignments
                WHERE faculty_id = ? AND subject_id = ? AND year = ? AND section = ?
                """,
                (fac_id, subject_id, st["year"], st["section"])
            ).fetchone()
            if not has_assign:
                return jsonify({
                    "error": "Access denied. Faculty may only enter marks for authorized teaching assignments."
                }), 403

        connection.execute(
            """
            INSERT INTO marks
            (
                student_id,
                subject_id,
                assessment_name,
                marks_obtained,
                max_marks
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                student_id,
                subject_id,
                assessment_name,
                marks_obtained,
                max_marks
            )
        )

        connection.commit()

        return jsonify({
            "message": "Marks saved successfully"
        }), 201

    except Exception:
        return jsonify({
            "error": "Unable to save marks. Check student and subject selections."
        }), 400

    finally:
        connection.close()


@app.route("/api/marks", methods=["GET"])
def get_marks():

    connection = get_db_connection()

    try:
        marks = connection.execute(
            """
            SELECT
                marks.mark_id,
                marks.student_id,
                marks.subject_id,
                students.roll_number,
                students.full_name,
                subjects.subject_code,
                subjects.subject_name,
                marks.assessment_name,
                marks.marks_obtained,
                marks.max_marks,
                marks.recorded_on
            FROM marks
            JOIN students
                ON marks.student_id = students.student_id
            JOIN subjects
                ON marks.subject_id = subjects.subject_id
            ORDER BY marks.mark_id ASC
            """
        ).fetchall()

        return jsonify([
            dict(mark) for mark in marks
        ])

    finally:
        connection.close()


@app.route("/api/marks/<int:mark_id>", methods=["PUT"])
def update_marks(mark_id):
    if session.get("role") == "student":
        return jsonify({"error": "Access denied. Action prohibited for student accounts."}), 403

    data = request.get_json(silent=True) or {}

    try:
        student_id = int(data.get("student_id"))
        subject_id = int(data.get("subject_id"))

        assessment_name = str(
            data.get("assessment_name", "")
        ).strip()

        marks_obtained = float(data.get("marks_obtained"))
        max_marks = float(data.get("max_marks"))

        if not assessment_name:
            return jsonify({
                "error": "Assessment name is required"
            }), 400

        if marks_obtained < 0 or max_marks <= 0:
            return jsonify({
                "error": "Invalid marks. Maximum marks must be greater than zero."
            }), 400

        if marks_obtained > max_marks:
            return jsonify({
                "error": "Marks obtained cannot exceed maximum marks"
            }), 400

    except (ValueError, TypeError):
        return jsonify({
            "error": "Please enter valid marks and selections"
        }), 400

    connection = get_db_connection()

    try:
        existing = connection.execute(
            "SELECT mark_id FROM marks WHERE mark_id = ?",
            (mark_id,)
        ).fetchone()

        if not existing:
            return jsonify({
                "error": "Marks record not found"
            }), 404

        student = connection.execute(
            "SELECT student_id FROM students WHERE student_id = ?",
            (student_id,)
        ).fetchone()

        if not student:
            return jsonify({
                "error": "Selected student does not exist"
            }), 400

        subject = connection.execute(
            "SELECT subject_id FROM subjects WHERE subject_id = ?",
            (subject_id,)
        ).fetchone()

        if not subject:
            return jsonify({
                "error": "Selected subject does not exist"
            }), 400

        # Section-level authorization for faculty editing marks
        if session.get("role") == "faculty":
            fac_id = session.get("faculty_id")
            st_row = connection.execute(
                "SELECT year, section FROM students WHERE student_id = ?", (student_id,)
            ).fetchone()
            if not st_row:
                return jsonify({"error": "Student not found"}), 404
            has_assign = connection.execute(
                "SELECT assignment_id FROM faculty_assignments WHERE faculty_id=? AND subject_id=? AND year=? AND section=?",
                (fac_id, subject_id, st_row["year"], st_row["section"])
            ).fetchone()
            if not has_assign:
                return jsonify({"error": "Access denied. Faculty may only edit marks for authorized teaching assignments."}), 403

        connection.execute(
            """
            UPDATE marks
            SET student_id = ?,
                subject_id = ?,
                assessment_name = ?,
                marks_obtained = ?,
                max_marks = ?
            WHERE mark_id = ?
            """,
            (
                student_id,
                subject_id,
                assessment_name,
                marks_obtained,
                max_marks,
                mark_id
            )
        )

        connection.commit()

        return jsonify({
            "message": "Marks updated successfully"
        }), 200

    except Exception:
        return jsonify({
            "error": "Unable to update marks record"
        }), 500

    finally:
        connection.close()


@app.route("/api/marks/<int:mark_id>", methods=["DELETE"])
def delete_marks(mark_id):
    if session.get("role") == "student":
        return jsonify({"error": "Access denied. Action prohibited for student accounts."}), 403

    connection = get_db_connection()

    try:
        existing = connection.execute(
            "SELECT mark_id FROM marks WHERE mark_id = ?",
            (mark_id,)
        ).fetchone()

        if not existing:
            return jsonify({
                "error": "Marks record not found"
            }), 404

        connection.execute(
            "DELETE FROM marks WHERE mark_id = ?",
            (mark_id,)
        )

        connection.commit()

        return jsonify({
            "message": "Marks record deleted successfully"
        }), 200

    except Exception:
        return jsonify({
            "error": "Unable to delete marks record"
        }), 500

    finally:
        connection.close()


# --------------------------------------------------
# ATTENDANCE MANAGEMENT
# --------------------------------------------------

@app.route("/api/attendance", methods=["POST"])
def save_attendance():
    if session.get("role") == "student":
        return jsonify({"error": "Access denied. Action prohibited for student accounts."}), 403

    data = request.get_json(silent=True) or {}

    try:
        student_id = int(data.get("student_id"))
        subject_id = int(data.get("subject_id"))
        total_classes = int(data.get("total_classes"))
        attended_classes = int(data.get("attended_classes"))

        if total_classes <= 0:
            return jsonify({
                "error": "Total classes must be greater than zero"
            }), 400

        if attended_classes < 0 or attended_classes > total_classes:
            return jsonify({
                "error": "Invalid attended classes"
            }), 400

    except (ValueError, TypeError):
        return jsonify({
            "error": "Please enter valid attendance details"
        }), 400

    connection = get_db_connection()

    try:
        if session.get("role") == "faculty":
            fac_id = session.get("faculty_id")
            st = connection.execute(
                "SELECT year, section, department FROM students WHERE student_id = ?",
                (student_id,)
            ).fetchone()
            if not st:
                return jsonify({"error": "Student not found"}), 404
            has_assign = connection.execute(
                """
                SELECT assignment_id FROM faculty_assignments
                WHERE faculty_id = ? AND subject_id = ? AND year = ? AND section = ?
                """,
                (fac_id, subject_id, st["year"], st["section"])
            ).fetchone()
            if not has_assign:
                return jsonify({
                    "error": "Access denied. Faculty may only record attendance for authorized teaching assignments."
                }), 403

        connection.execute(
            """
            INSERT INTO attendance
            (
                student_id,
                subject_id,
                total_classes,
                attended_classes
            )
            VALUES (?, ?, ?, ?)

            ON CONFLICT(student_id, subject_id)
            DO UPDATE SET
                total_classes = excluded.total_classes,
                attended_classes = excluded.attended_classes,
                updated_on = CURRENT_DATE
            """,
            (
                student_id,
                subject_id,
                total_classes,
                attended_classes
            )
        )

        connection.commit()

        return jsonify({
            "message": "Attendance saved successfully"
        }), 201

    except Exception:
        return jsonify({
            "error": "Unable to save attendance"
        }), 400

    finally:
        connection.close()


@app.route("/api/attendance", methods=["GET"])
def get_attendance():

    connection = get_db_connection()

    try:
        records = connection.execute(
            """
            SELECT
                attendance.attendance_id,
                students.roll_number,
                students.full_name,
                subjects.subject_code,
                subjects.subject_name,
                attendance.total_classes,
                attendance.attended_classes,

                ROUND(
                    100.0 * attendance.attended_classes /
                    NULLIF(attendance.total_classes, 0), 2
                ) AS attendance_percentage

            FROM attendance

            JOIN students
                ON attendance.student_id = students.student_id

            JOIN subjects
                ON attendance.subject_id = subjects.subject_id

            ORDER BY attendance.attendance_id ASC
            """
        ).fetchall()

        return jsonify([
            dict(record) for record in records
        ])

    finally:
        connection.close()


@app.route("/api/attendance/<int:attendance_id>", methods=["PUT"])
def update_attendance(attendance_id):
    if session.get("role") == "student":
        return jsonify({"error": "Access denied. Action prohibited for student accounts."}), 403

    data = request.get_json(silent=True) or {}

    try:
        total_classes = int(data.get("total_classes"))
        attended_classes = int(data.get("attended_classes"))

        if total_classes <= 0:
            return jsonify({
                "error": "Total classes must be greater than zero"
            }), 400

        if attended_classes < 0 or attended_classes > total_classes:
            return jsonify({
                "error": "Attended classes must be between 0 and total classes"
            }), 400

    except (ValueError, TypeError):
        return jsonify({
            "error": "Please enter valid attendance details"
        }), 400

    connection = get_db_connection()

    try:
        existing = connection.execute(
            "SELECT attendance_id, student_id, subject_id FROM attendance WHERE attendance_id = ?",
            (attendance_id,)
        ).fetchone()

        if not existing:
            return jsonify({"error": "Attendance record not found"}), 404

        # Section-level authorization for faculty editing attendance
        if session.get("role") == "faculty":
            fac_id = session.get("faculty_id")
            st_row = connection.execute(
                "SELECT year, section FROM students WHERE student_id=?", (existing["student_id"],)
            ).fetchone()
            if not st_row:
                return jsonify({"error": "Student not found"}), 404
            has_assign = connection.execute(
                "SELECT assignment_id FROM faculty_assignments WHERE faculty_id=? AND subject_id=? AND year=? AND section=?",
                (fac_id, existing["subject_id"], st_row["year"], st_row["section"])
            ).fetchone()
            if not has_assign:
                return jsonify({"error": "Access denied. Faculty may only edit attendance for authorized teaching assignments."}), 403

        connection.execute(
            """
            UPDATE attendance
            SET
                total_classes = ?,
                attended_classes = ?,
                updated_on = CURRENT_DATE
            WHERE attendance_id = ?
            """,
            (total_classes, attended_classes, attendance_id)
        )

        connection.commit()

        return jsonify({"message": "Attendance updated successfully"}), 200

    except Exception:
        return jsonify({"error": "Unable to update attendance"}), 400

    finally:
        connection.close()


@app.route("/api/attendance/<int:attendance_id>", methods=["DELETE"])
def delete_attendance(attendance_id):
    if session.get("role") == "student":
        return jsonify({"error": "Access denied. Action prohibited for student accounts."}), 403

    connection = get_db_connection()

    try:
        existing = connection.execute(
            "SELECT attendance_id, student_id, subject_id FROM attendance WHERE attendance_id = ?",
            (attendance_id,)
        ).fetchone()

        if not existing:
            return jsonify({"error": "Attendance record not found"}), 404

        # Section-level authorization for faculty editing attendance
        if session.get("role") == "faculty":
            fac_id = session.get("faculty_id")
            st_row = connection.execute(
                "SELECT year, section FROM students WHERE student_id=?", (existing["student_id"],)
            ).fetchone()
            if not st_row:
                return jsonify({"error": "Student not found"}), 404
            has_assign = connection.execute(
                "SELECT assignment_id FROM faculty_assignments WHERE faculty_id=? AND subject_id=? AND year=? AND section=?",
                (fac_id, existing["subject_id"], st_row["year"], st_row["section"])
            ).fetchone()
            if not has_assign:
                return jsonify({"error": "Access denied. Faculty may only edit attendance for authorized teaching assignments."}), 403

        connection.execute(
            "DELETE FROM attendance WHERE attendance_id = ?",
            (attendance_id,)
        )

        connection.commit()

        return jsonify({"message": "Attendance record deleted successfully"}), 200

    except Exception:
        return jsonify({"error": "Unable to delete attendance record"}), 400

    finally:
        connection.close()


@app.route("/api/attendance/<int:attendance_id>", methods=["GET"])
def get_single_attendance(attendance_id):

    connection = get_db_connection()

    try:
        record = connection.execute(
            """
            SELECT
                a.attendance_id,
                a.student_id,
                a.subject_id,
                s.roll_number,
                s.full_name,
                sub.subject_code,
                sub.subject_name,
                a.total_classes,
                a.attended_classes,
                ROUND(
                    100.0 * a.attended_classes / NULLIF(a.total_classes, 0), 2
                ) AS attendance_percentage
            FROM attendance a
            JOIN students s ON a.student_id = s.student_id
            JOIN subjects sub ON a.subject_id = sub.subject_id
            WHERE a.attendance_id = ?
            """,
            (attendance_id,)
        ).fetchone()

        if not record:
            return jsonify({"error": "Attendance record not found"}), 404

        return jsonify(dict(record)), 200

    finally:
        connection.close()


# --------------------------------------------------
# STUDENT PERFORMANCE OVERVIEW
# --------------------------------------------------

@app.route("/api/performance", methods=["GET"])
def get_performance():
    if session.get("role") == "student":
        return jsonify({"error": "Access denied. Students cannot access cohort performance records."}), 403

    connection = get_db_connection()

    try:
        students = connection.execute(
            """
            SELECT *
            FROM students
            ORDER BY student_id ASC
            """
        ).fetchall()

        results = []

        for student in students:

            marks = connection.execute(
                """
                SELECT
                    SUM(marks_obtained) AS obtained,
                    SUM(max_marks) AS maximum
                FROM marks
                WHERE student_id = ?
                """,
                (student["student_id"],)
            ).fetchone()

            attendance = connection.execute(
                """
                SELECT
                    SUM(attended_classes) AS attended,
                    SUM(total_classes) AS total
                FROM attendance
                WHERE student_id = ?
                """,
                (student["student_id"],)
            ).fetchone()

            average_marks = None
            attendance_percentage = None

            if marks["maximum"] and marks["maximum"] > 0:
                average_marks = round(
                    100 * marks["obtained"] / marks["maximum"], 2
                )

            if attendance["total"] and attendance["total"] > 0:
                attendance_percentage = round(
                    100 * attendance["attended"] / attendance["total"], 2
                )

            risk = calculate_risk(
                average_marks,
                attendance_percentage
            )

            results.append({
                "student_id": student["student_id"],
                "roll_number": student["roll_number"],
                "student_name": student["full_name"],
                "average_marks": average_marks,
                "attendance_percentage": attendance_percentage,
                "risk_level": risk
            })

        return jsonify(results)

    finally:
        connection.close()


# --------------------------------------------------
# INDIVIDUAL STUDENT ANALYSIS API
# --------------------------------------------------

@app.route(
    "/api/students/<int:student_id>/analysis",
    methods=["GET"]
)
def student_analysis(student_id):
    role = session.get("role")
    if role == "student" and session.get("student_id") != student_id:
        return jsonify({"error": "Access denied. Students may only access their own academic records."}), 403

    data = get_student_analysis_data(student_id)

    if data is None:
        return jsonify({
            "error": "Student not found"
        }), 404

    return jsonify(data)


# --------------------------------------------------
# LOCAL AI INSIGHTS USING OLLAMA
# --------------------------------------------------

@app.route(
    "/api/students/<int:student_id>/ai-insights",
    methods=["POST"]
)
def student_ai_insights(student_id):
    role = session.get("role")
    if role == "student" and session.get("student_id") != student_id:
        return jsonify({"error": "Access denied. Students may only access their own academic records."}), 403

    # Retrieve student data directly from SQLite
    student_data = get_student_analysis_data(student_id)

    if student_data is None:
        return jsonify({
            "error": "Student not found"
        }), 404

    if student_data["risk_level"] == "Insufficient Data":
        return jsonify({
            "error": "Insufficient marks or attendance data to generate insights."
        }), 400

    # Prepare subject-level breakdown
    marks_breakdown = "\n".join([
        f"- {m['subject_code']} ({m['subject_name']}): {m['assessment_name']} - {m['marks_obtained']}/{m['max_marks']} ({m['percentage']}%)"
        for m in student_data.get("marks", [])
    ]) or "No subject assessment records."

    att_breakdown = "\n".join([
        f"- {a['subject_code']} ({a['subject_name']}): {a['attended_classes']}/{a['total_classes']} classes attended ({a['percentage']}%)"
        for a in student_data.get("attendance", [])
    ]) or "No subject attendance records."

    # Prepare the AI prompt
    prompt = f"""
You are an educational performance analysis assistant for EduTrack Lite.

Your task is to help faculty understand student performance using
only the student records provided below.

STUDENT DATA:
Student: {student_data['student']['full_name']}
Department: {student_data['student']['department']}
Average Marks: {student_data['average_marks']}%
Attendance: {student_data['attendance_percentage']}%
Existing Risk Classification: {student_data['risk_level']}

RECORDED SUBJECT MARKS:
{marks_breakdown}

RECORDED SUBJECT ATTENDANCE:
{att_breakdown}

RISK CLASSIFICATION RULES USED BY THE APPLICATION:
- High: Average marks below 40% OR attendance below 65%.
- Medium: Average marks below 60% OR attendance below 75%.
- Low: Average marks at least 60% AND attendance at least 75%.
- Insufficient Data: Required academic or attendance information is missing.

These are application-defined indicators, not official university policies.

ANALYSIS REQUIRED:

1. Risk Classification Explanation
- Explain the existing classification using the supplied measurements.
- Discuss marks and attendance separately.
- Identify which available measurement contributes to the classification.
- Do not change or recalculate the classification.

2. Visible Strengths
- Mention only strengths directly supported by recorded data.
- Describe high marks only as strong recorded academic performance.
- Use the exact recorded average where available.
- Never use words like "consistent", "improved" or "maintained"
  unless multiple time-based records support that conclusion.
- Do not claim mastery, intelligence, discipline, resilience or good study habits.
- If no clear strength can be established, say so.

3. Areas Needing Improvement
- Identify measurable areas that need attention.
- Explain the recorded gap objectively.
- Describe attendance only as a recorded percentage.
- Do not claim that absences caused missed learning,
  reduced participation or affected peer interaction.
- Do not assume the reasons behind the measurements.
- Do not describe a student as careless, disengaged or unmotivated.

4. Practical and Supportive Recommendations
- Give exactly three actionable recommendations.
- Each recommendation must address an identified improvement area.
- Make recommendations realistic and supportive.
- Do not recommend punishment or disciplinary action.

STRICT RULES:
- Never describe an application threshold as an official
  university or institutional benchmark.
- Refer to 75% only as the application's Low Risk threshold.
- Do not infer academic consistency from a single average.
- Do not claim consequences of absences unless supported
  by specific records.
- Accept the supplied risk classification as correct.
- Never modify the risk classification.
- Treat marks and attendance as measurements, not explanations of behaviour.
- Never invent achievements, activities, performance history or personal circumstances.
- Never assume health, financial, family or personal problems.
- Never predict failure, dropout or future academic outcomes.
- Never claim that a student has improved or declined without historical data.
- Do not invent institutional policies or attendance requirements.
- Clearly distinguish recorded facts from suggestions.
- If information is unavailable, explicitly mention that it is unavailable.
- Use respectful, neutral and non-punitive language.

OUTPUT FORMAT:

Use these four headings exactly:
1. Risk Classification Explanation
2. Visible Strengths
3. Areas Needing Improvement
4. Practical and Supportive Recommendations

Keep the report between 200 and 300 words.
Include exactly three numbered recommendations.
Complete all four sections.
Do not include internal reasoning or repeat the entire dataset.
"""

    # Prepare Ollama request
    ollama_payload = {
        "model": "qwen3.5:4b",
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "stream": False,
        "think": False,
        "options": {
            "num_predict": 700
        }
    }

    ollama_request = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=json.dumps(ollama_payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(
            ollama_request,
            timeout=60
        ) as response:

            result = json.loads(
                response.read().decode("utf-8")
            )

        insights = result.get("message", {}).get("content", "").strip()

        # Clean thinking tags if present in model output
        insights = re.sub(r"<think>.*?</think>", "", insights, flags=re.DOTALL).strip()

        if not insights:
            insights = generate_heuristic_ai_insights(student_data)

        return jsonify({
            "student_name": student_data["student"]["full_name"],
            "risk_level": student_data["risk_level"],
            "insights": insights,
            "engine": "ollama"
        })

    except Exception as error:
        app.logger.warning(f"Ollama insight call failed: {error}. Falling back to Academic Heuristic Engine.")
        fallback_insights = generate_heuristic_ai_insights(student_data)

        return jsonify({
            "student_name": student_data["student"]["full_name"],
            "risk_level": student_data["risk_level"],
            "insights": fallback_insights,
            "engine": "heuristic_fallback",
            "notice": "Ollama service unavailable. Insights generated via EduTrack Lite Academic Heuristic Engine."
        })


# --------------------------------------------------
# INDIVIDUAL STUDENT ANALYSIS PAGE
# --------------------------------------------------

@app.route("/student-analysis")
def student_analysis_page():
    user = get_current_user()
    if not user:
        return redirect(url_for("login_page"))
    if user["role"] == "student":
        return redirect(url_for("student_dashboard"))
    return render_template("student_analysis.html", user=user)


# --------------------------------------------------
# FACULTY MANAGEMENT & ASSIGNMENTS API
# --------------------------------------------------

@app.route("/api/faculty", methods=["GET"])
def get_faculty_list():
    if session.get("role") == "student":
        return jsonify({"error": "Access denied. Students cannot access faculty directory."}), 403
    connection = get_db_connection()
    try:
        faculty = connection.execute(
            """
            SELECT
                f.faculty_id,
                f.user_id,
                f.full_name,
                f.department,
                f.email,
                u.username,
                COUNT(fa.assignment_id) AS assignment_count
            FROM faculty f
            JOIN users u ON f.user_id = u.user_id
            LEFT JOIN faculty_assignments fa ON f.faculty_id = fa.faculty_id
            GROUP BY f.faculty_id
            ORDER BY f.faculty_id ASC
            """
        ).fetchall()
        return jsonify([dict(row) for row in faculty])
    finally:
        connection.close()


@app.route("/api/faculty", methods=["POST"])
def add_faculty():
    if session.get("role") == "student":
        return jsonify({"error": "Access denied. Action prohibited for student accounts."}), 403
    data = request.get_json(silent=True) or {}
    full_name = str(data.get("full_name", "")).strip()
    department = str(data.get("department", "")).strip()
    email = str(data.get("email", "")).strip() or None
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", "")).strip()

    if not full_name or not department or not username or not password:
        return jsonify({"error": "Full name, department, username, and password are required"}), 400

    connection = get_db_connection()
    try:
        existing_user = connection.execute(
            "SELECT user_id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if existing_user:
            return jsonify({"error": "Username already exists"}), 409

        if email:
            existing_email = connection.execute(
                "SELECT faculty_id FROM faculty WHERE email = ?", (email,)
            ).fetchone()
            if existing_email:
                return jsonify({"error": "Email already registered to another faculty member"}), 409

        pass_hash = generate_password_hash(password)
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'faculty')",
            (username, pass_hash)
        )
        user_id = cursor.lastrowid

        cursor.execute(
            """
            INSERT INTO faculty (user_id, full_name, department, email)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, full_name, department, email)
        )
        connection.commit()
        return jsonify({"message": "Faculty member added successfully"}), 201

    except Exception as error:
        connection.rollback()
        return jsonify({"error": f"Unable to add faculty: {str(error)}"}), 500
    finally:
        connection.close()


@app.route("/api/faculty/<int:faculty_id>", methods=["PUT"])
def update_faculty(faculty_id):
    if session.get("role") == "student":
        return jsonify({"error": "Access denied. Action prohibited for student accounts."}), 403
    data = request.get_json(silent=True) or {}
    full_name = str(data.get("full_name", "")).strip()
    department = str(data.get("department", "")).strip()
    email = str(data.get("email", "")).strip() or None

    if not full_name or not department:
        return jsonify({"error": "Full name and department are required"}), 400

    connection = get_db_connection()
    try:
        fac = connection.execute(
            "SELECT faculty_id FROM faculty WHERE faculty_id = ?", (faculty_id,)
        ).fetchone()
        if not fac:
            return jsonify({"error": "Faculty not found"}), 404

        if email:
            duplicate_email = connection.execute(
                "SELECT faculty_id FROM faculty WHERE email = ? AND faculty_id != ?",
                (email, faculty_id)
            ).fetchone()
            if duplicate_email:
                return jsonify({"error": "Email already in use by another faculty member"}), 409

        connection.execute(
            """
            UPDATE faculty
            SET full_name = ?, department = ?, email = ?
            WHERE faculty_id = ?
            """,
            (full_name, department, email, faculty_id)
        )
        connection.commit()
        return jsonify({"message": "Faculty details updated successfully"}), 200
    finally:
        connection.close()


@app.route("/api/faculty/<int:faculty_id>", methods=["DELETE"])
def delete_faculty(faculty_id):
    if session.get("role") == "student":
        return jsonify({"error": "Access denied. Action prohibited for student accounts."}), 403
    connection = get_db_connection()
    try:
        fac = connection.execute(
            "SELECT faculty_id, user_id FROM faculty WHERE faculty_id = ?", (faculty_id,)
        ).fetchone()
        if not fac:
            return jsonify({"error": "Faculty not found"}), 404

        assignments_count = connection.execute(
            "SELECT COUNT(*) FROM faculty_assignments WHERE faculty_id = ?", (faculty_id,)
        ).fetchone()[0]

        if assignments_count > 0:
            return jsonify({
                "error": f"Cannot delete faculty member: {assignments_count} active teaching assignment(s) exist. Remove assignments first."
            }), 409

        user_id = fac["user_id"]
        connection.execute("DELETE FROM faculty WHERE faculty_id = ?", (faculty_id,))
        connection.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        connection.commit()
        return jsonify({"message": "Faculty member removed successfully"}), 200
    finally:
        connection.close()


@app.route("/api/faculty-assignments", methods=["GET"])
def get_faculty_assignments():
    if session.get("role") == "student":
        return jsonify({"error": "Access denied. Students cannot access faculty assignments."}), 403
    connection = get_db_connection()
    try:
        assignments = connection.execute(
            """
            SELECT
                fa.assignment_id,
                fa.faculty_id,
                f.full_name AS faculty_name,
                COALESCE(fa.department, f.department) AS faculty_department,
                fa.subject_id,
                s.subject_code,
                s.subject_name,
                fa.year,
                fa.section
            FROM faculty_assignments fa
            JOIN faculty f ON fa.faculty_id = f.faculty_id
            JOIN subjects s ON fa.subject_id = s.subject_id
            ORDER BY fa.year ASC, fa.section ASC, s.subject_code ASC
            """
        ).fetchall()
        return jsonify([dict(row) for row in assignments])
    finally:
        connection.close()


@app.route("/api/faculty-assignments/preview-students", methods=["GET"])
def preview_assignment_students():
    """Preview existing students matching department, year, and section for teaching assignment."""
    if session.get("role") != "coordinator":
        return jsonify({"error": "Access denied. Coordinator authorization required."}), 403

    dept = request.args.get("department", "").strip()
    year = request.args.get("year", "").strip()
    section = request.args.get("section", "").strip().upper()

    if not dept or not year or not section:
        return jsonify({"students": [], "count": 0}), 200

    try:
        year_num = int(year)
    except ValueError:
        return jsonify({"students": [], "count": 0}), 200

    connection = get_db_connection()
    try:
        rows = connection.execute(
            """
            SELECT student_id, roll_number, full_name, department, year, section
            FROM students
            WHERE department = ? AND year = ? AND section = ?
            ORDER BY roll_number ASC
            """,
            (dept, year_num, section)
        ).fetchall()
        return jsonify({
            "students": [dict(r) for r in rows],
            "count": len(rows)
        }), 200
    finally:
        connection.close()


@app.route("/api/faculty-assignments", methods=["POST"])
def add_faculty_assignment():
    if session.get("role") != "coordinator":
        return jsonify({"error": "Access denied. Coordinator authorization required."}), 403
    data = request.get_json(silent=True) or {}
    try:
        faculty_id = int(data.get("faculty_id"))
        subject_id = int(data.get("subject_id"))
        year = int(data.get("year"))
        section = str(data.get("section", "")).strip().upper()
        department = str(data.get("department", "")).strip()

        if not section:
            return jsonify({"error": "Section is required"}), 400
        if year < 1 or year > 6:
            return jsonify({"error": "Invalid academic year"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "Please enter valid assignment details"}), 400

    connection = get_db_connection()
    try:
        if not department:
            fac = connection.execute("SELECT department FROM faculty WHERE faculty_id = ?", (faculty_id,)).fetchone()
            if fac:
                department = fac["department"]

        connection.execute(
            """
            INSERT INTO faculty_assignments (faculty_id, subject_id, year, section, department)
            VALUES (?, ?, ?, ?, ?)
            """,
            (faculty_id, subject_id, year, section, department)
        )
        connection.commit()
        return jsonify({"message": "Faculty assignment created successfully"}), 201
    except Exception as error:
        if "UNIQUE constraint failed" in str(error):
            return jsonify({"error": "This teaching assignment already exists"}), 409
        return jsonify({"error": "Unable to save faculty assignment"}), 500
    finally:
        connection.close()


@app.route("/api/faculty-assignments/<int:assignment_id>", methods=["DELETE"])
def delete_faculty_assignment(assignment_id):
    if session.get("role") != "coordinator":
        return jsonify({"error": "Access denied. Coordinator authorization required."}), 403
    connection = get_db_connection()
    try:
        connection.execute(
            "DELETE FROM faculty_assignments WHERE assignment_id = ?",
            (assignment_id,)
        )
        connection.commit()
        return jsonify({"message": "Assignment removed successfully"}), 200
    finally:
        connection.close()


# --------------------------------------------------
# CLASS ADVISOR MANAGEMENT API
# --------------------------------------------------

@app.route("/api/class-advisors", methods=["GET"])
def get_class_advisors():
    """List all active Class Advisor assignments."""
    if session.get("role") != "coordinator":
        return jsonify({"error": "Access denied. Coordinator authorization required."}), 403

    connection = get_db_connection()
    try:
        rows = connection.execute("""
            SELECT
                caa.assignment_id,
                caa.faculty_id,
                f.full_name AS faculty_name,
                f.department AS faculty_department,
                f.email AS faculty_email,
                caa.student_id,
                s.roll_number,
                s.full_name AS student_name,
                s.department AS student_department,
                s.year AS student_year,
                s.section AS student_section,
                caa.assigned_at,
                caa.is_active
            FROM class_advisor_assignments caa
            JOIN faculty f ON caa.faculty_id = f.faculty_id
            JOIN students s ON caa.student_id = s.student_id
            WHERE caa.is_active = 1
            ORDER BY s.department ASC, s.year ASC, s.section ASC, s.roll_number ASC
        """).fetchall()
        return jsonify([dict(r) for r in rows]), 200
    finally:
        connection.close()


@app.route("/api/class-advisors/preview", methods=["GET"])
def preview_class_advisor_students():
    """Preview students for section-level Class Advisor assignment showing current advisor if any."""
    if session.get("role") != "coordinator":
        return jsonify({"error": "Access denied. Coordinator authorization required."}), 403

    dept = request.args.get("department", "").strip()
    year = request.args.get("year", "").strip()
    section = request.args.get("section", "").strip().upper()

    if not dept or not year or not section:
        return jsonify({"students": [], "count": 0}), 200

    try:
        year_num = int(year)
    except ValueError:
        return jsonify({"students": [], "count": 0}), 200

    connection = get_db_connection()
    try:
        rows = connection.execute("""
            SELECT
                s.student_id,
                s.roll_number,
                s.full_name,
                s.department,
                s.year,
                s.section,
                f.faculty_id AS current_advisor_id,
                f.full_name AS current_advisor_name
            FROM students s
            LEFT JOIN class_advisor_assignments caa ON s.student_id = caa.student_id AND caa.is_active = 1
            LEFT JOIN faculty f ON caa.faculty_id = f.faculty_id
            WHERE s.department = ? AND s.year = ? AND s.section = ?
            ORDER BY s.roll_number ASC
        """, (dept, year_num, section)).fetchall()

        return jsonify({
            "students": [dict(r) for r in rows],
            "count": len(rows)
        }), 200
    finally:
        connection.close()


@app.route("/api/class-advisors/bulk", methods=["POST"])
def assign_class_advisor_bulk():
    """Assign a faculty member as Class Advisor to all students in a section."""
    if session.get("role") != "coordinator":
        return jsonify({"error": "Access denied. Coordinator authorization required."}), 403

    data = request.get_json(silent=True) or {}
    try:
        faculty_id = int(data.get("faculty_id"))
        dept = str(data.get("department", "")).strip()
        year = int(data.get("year"))
        section = str(data.get("section", "")).strip().upper()
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid input parameters for Class Advisor assignment."}), 400

    if not dept or not section or year < 1:
        return jsonify({"error": "Department, year, and section are required."}), 400

    connection = get_db_connection()
    try:
        fac = connection.execute(
            "SELECT faculty_id, full_name, department FROM faculty WHERE faculty_id = ?",
            (faculty_id,)
        ).fetchone()
        if not fac:
            return jsonify({"error": "Faculty member not found."}), 404

        students = connection.execute(
            "SELECT student_id, full_name FROM students WHERE department = ? AND year = ? AND section = ?",
            (dept, year, section)
        ).fetchall()

        if not students:
            return jsonify({"error": f"No existing students found matching {dept} Year {year} Section {section}."}), 404

        # In transaction: deactivate existing active advisor and insert new advisor
        cursor = connection.cursor()
        for st in students:
            cursor.execute(
                "UPDATE class_advisor_assignments SET is_active = 0 WHERE student_id = ? AND is_active = 1",
                (st["student_id"],)
            )
            cursor.execute(
                """
                INSERT INTO class_advisor_assignments (faculty_id, student_id, is_active)
                VALUES (?, ?, 1)
                """,
                (faculty_id, st["student_id"])
            )

        connection.commit()
        return jsonify({
            "message": f"Successfully assigned {fac['full_name']} as Class Advisor to {len(students)} student(s) in {dept} Year {year} Section {section}."
        }), 200
    except Exception as e:
        connection.rollback()
        return jsonify({"error": f"Unable to assign Class Advisor: {str(e)}"}), 500
    finally:
        connection.close()


@app.route("/api/class-advisors/assign-student", methods=["POST"])
def assign_class_advisor_individual():
    """Assign or change Class Advisor for an individual student."""
    if session.get("role") != "coordinator":
        return jsonify({"error": "Access denied. Coordinator authorization required."}), 403

    data = request.get_json(silent=True) or {}
    try:
        student_id = int(data.get("student_id"))
        faculty_id = int(data.get("faculty_id"))
    except (ValueError, TypeError):
        return jsonify({"error": "Valid student ID and faculty ID are required."}), 400

    connection = get_db_connection()
    try:
        student = connection.execute(
            "SELECT student_id, full_name FROM students WHERE student_id = ?",
            (student_id,)
        ).fetchone()
        if not student:
            return jsonify({"error": "Student record not found."}), 404

        faculty = connection.execute(
            "SELECT faculty_id, full_name FROM faculty WHERE faculty_id = ?",
            (faculty_id,)
        ).fetchone()
        if not faculty:
            return jsonify({"error": "Faculty member not found."}), 404

        cursor = connection.cursor()
        cursor.execute(
            "UPDATE class_advisor_assignments SET is_active = 0 WHERE student_id = ? AND is_active = 1",
            (student_id,)
        )
        cursor.execute(
            """
            INSERT INTO class_advisor_assignments (faculty_id, student_id, is_active)
            VALUES (?, ?, 1)
            """,
            (faculty_id, student_id)
        )
        connection.commit()

        return jsonify({
            "message": f"Assigned {faculty['full_name']} as Class Advisor for {student['full_name']}."
        }), 200
    except Exception as e:
        connection.rollback()
        return jsonify({"error": f"Unable to assign Class Advisor: {str(e)}"}), 500
    finally:
        connection.close()


@app.route("/api/class-advisors/<int:assignment_id>", methods=["DELETE"])
def remove_class_advisor_assignment(assignment_id):
    """Deactivate a Class Advisor assignment."""
    if session.get("role") != "coordinator":
        return jsonify({"error": "Access denied. Coordinator authorization required."}), 403

    connection = get_db_connection()
    try:
        existing = connection.execute(
            "SELECT assignment_id FROM class_advisor_assignments WHERE assignment_id = ?",
            (assignment_id,)
        ).fetchone()
        if not existing:
            return jsonify({"error": "Advisor assignment not found."}), 404

        connection.execute(
            "UPDATE class_advisor_assignments SET is_active = 0 WHERE assignment_id = ?",
            (assignment_id,)
        )
        connection.commit()
        return jsonify({"message": "Class Advisor assignment removed successfully."}), 200
    finally:
        connection.close()


# --------------------------------------------------
# FACULTY DASHBOARD API
# --------------------------------------------------

@app.route("/api/faculty/<int:faculty_id>/dashboard", methods=["GET"])
def get_faculty_dashboard_data(faculty_id):
    role = session.get("role")
    if role == "student":
        return jsonify({"error": "Access denied. Students cannot access faculty data."}), 403

    connection = get_db_connection()

    try:
        # If faculty_id == 0, detect from session or default to first faculty
        if faculty_id == 0:
            sess_fac = session.get("faculty_id")
            if sess_fac:
                faculty_id = sess_fac
            else:
                first = connection.execute(
                    "SELECT faculty_id FROM faculty ORDER BY faculty_id ASC LIMIT 1"
                ).fetchone()
                if first:
                    faculty_id = first["faculty_id"]
                else:
                    return jsonify({"error": "No faculty members found"}), 404

        faculty = connection.execute("""
            SELECT faculty_id, full_name, department, email
            FROM faculty
            WHERE faculty_id = ?
        """, (faculty_id,)).fetchone()

        if not faculty:
            return jsonify({"error": "Faculty not found"}), 404

        assignments = connection.execute("""
            SELECT
                fa.assignment_id,
                s.subject_id,
                s.subject_code,
                s.subject_name,
                fa.year,
                fa.section
            FROM faculty_assignments fa
            JOIN subjects s ON fa.subject_id = s.subject_id
            WHERE fa.faculty_id = ?
            ORDER BY fa.year, fa.section, s.subject_code
        """, (faculty_id,)).fetchall()

        # Derive enrolled students from actual marks/attendance records, restricted
        # by BOTH subject_id AND the specific year+section the faculty is assigned to.
        # This enforces strict section isolation: EK faculty cannot see KJ students
        # and vice versa, even if both teach the same subject.
        students = connection.execute("""
            SELECT DISTINCT
                st.student_id,
                st.roll_number,
                st.full_name,
                st.department,
                st.year,
                st.section
            FROM students st
            JOIN (
                SELECT DISTINCT student_id, subject_id FROM marks
                UNION
                SELECT DISTINCT student_id, subject_id FROM attendance
            ) enrol ON enrol.student_id = st.student_id
            JOIN faculty_assignments fa
                ON fa.subject_id = enrol.subject_id
                AND fa.faculty_id = ?
                AND fa.year = st.year
                AND fa.section = st.section
            ORDER BY st.roll_number ASC
        """, (faculty_id,)).fetchall()

        student_ids = [student["student_id"] for student in students]
        subject_ids = list({
            assignment["subject_id"] for assignment in assignments
        })

        assigned_marks = []
        assigned_attendance = []
        assigned_performance = []

        if student_ids and subject_ids:
            student_placeholders = ",".join("?" * len(student_ids))
            subject_placeholders = ",".join("?" * len(subject_ids))

            # Marks: restricted to students in this faculty's sections AND subjects
            # Uses a subquery to only include (student, subject) pairs the faculty
            # is actually authorized to view (matching year+section).
            assigned_marks = connection.execute(f"""
                SELECT
                    m.mark_id,
                    m.student_id,
                    m.subject_id,
                    st.roll_number,
                    st.full_name,
                    sub.subject_code,
                    sub.subject_name,
                    m.assessment_name,
                    m.marks_obtained,
                    m.max_marks,
                    m.recorded_on
                FROM marks m
                JOIN students st ON m.student_id = st.student_id
                JOIN subjects sub ON m.subject_id = sub.subject_id
                JOIN faculty_assignments fa
                    ON fa.subject_id = m.subject_id
                    AND fa.faculty_id = {faculty_id}
                    AND fa.year = st.year
                    AND fa.section = st.section
                WHERE m.student_id IN ({student_placeholders})
                AND m.subject_id IN ({subject_placeholders})
                ORDER BY m.mark_id DESC
            """, student_ids + subject_ids).fetchall()

            # Attendance: same section-aware restriction
            assigned_attendance = connection.execute(f"""
                SELECT
                    a.attendance_id,
                    a.student_id,
                    a.subject_id,
                    st.roll_number,
                    st.full_name,
                    sub.subject_code,
                    sub.subject_name,
                    a.total_classes,
                    a.attended_classes,
                    ROUND(
                        100.0 * a.attended_classes / NULLIF(a.total_classes, 0), 2
                    ) AS attendance_percentage
                FROM attendance a
                JOIN students st ON a.student_id = st.student_id
                JOIN subjects sub ON a.subject_id = sub.subject_id
                JOIN faculty_assignments fa
                    ON fa.subject_id = a.subject_id
                    AND fa.faculty_id = {faculty_id}
                    AND fa.year = st.year
                    AND fa.section = st.section
                WHERE a.student_id IN ({student_placeholders})
                AND a.subject_id IN ({subject_placeholders})
                ORDER BY a.attendance_id ASC
            """, student_ids + subject_ids).fetchall()

            for st in students:
                sid = st["student_id"]
                st_marks = [m for m in assigned_marks if m["student_id"] == sid]
                st_att = [a for a in assigned_attendance if a["student_id"] == sid]

                tot_obtained = sum(m["marks_obtained"] for m in st_marks)
                tot_max = sum(m["max_marks"] for m in st_marks)
                tot_attended = sum(a["attended_classes"] for a in st_att)
                tot_classes = sum(a["total_classes"] for a in st_att)

                avg_m = round(100.0 * tot_obtained / tot_max, 2) if tot_max > 0 else None
                att_p = round(100.0 * tot_attended / tot_classes, 2) if tot_classes > 0 else None
                risk = calculate_risk(avg_m, att_p)

                # Collect which of this faculty's subjects this student is enrolled in
                enrolled_subject_ids = list({m["subject_id"] for m in st_marks} | {a["subject_id"] for a in st_att})
                enrolled_subjects = [
                    {"subject_id": a["subject_id"], "subject_name": a["subject_name"], "subject_code": a["subject_code"]}
                    for a in assigned_marks if a["student_id"] == sid
                ]
                # De-duplicate subjects
                seen_sids = set()
                unique_enrolled = []
                for subj in enrolled_subjects:
                    if subj["subject_id"] not in seen_sids:
                        seen_sids.add(subj["subject_id"])
                        unique_enrolled.append(subj)

                assigned_performance.append({
                    "student_id": sid,
                    "roll_number": st["roll_number"],
                    "student_name": st["full_name"],
                    "department": st["department"],
                    "year": st["year"],
                    "section": st["section"],
                    "average_marks": avg_m,
                    "attendance_percentage": att_p,
                    "risk_level": risk,
                    "enrolled_subject_ids": enrolled_subject_ids,
                    "enrolled_subjects": unique_enrolled
                })

        # Query active advisees assigned to this faculty member as Class Advisor
        advisee_rows = connection.execute("""
            SELECT
                caa.assignment_id,
                s.student_id,
                s.roll_number,
                s.full_name,
                s.department,
                s.year,
                s.section,
                caa.assigned_at
            FROM class_advisor_assignments caa
            JOIN students s ON caa.student_id = s.student_id
            WHERE caa.faculty_id = ? AND caa.is_active = 1
            ORDER BY s.roll_number ASC
        """, (faculty_id,)).fetchall()

        advisees_list = []
        for adv in advisee_rows:
            sid = adv["student_id"]
            st_all_marks = connection.execute("""
                SELECT
                    m.mark_id,
                    m.assessment_name,
                    m.marks_obtained,
                    m.max_marks,
                    ROUND(100.0 * m.marks_obtained / NULLIF(m.max_marks, 0), 2) AS percentage,
                    s.subject_code,
                    s.subject_name
                FROM marks m
                JOIN subjects s ON m.subject_id = s.subject_id
                WHERE m.student_id = ?
                ORDER BY s.subject_code ASC, m.mark_id ASC
            """, (sid,)).fetchall()

            st_all_att = connection.execute("""
                SELECT
                    a.attendance_id,
                    a.total_classes,
                    a.attended_classes,
                    ROUND(100.0 * a.attended_classes / NULLIF(a.total_classes, 0), 2) AS attendance_percentage,
                    s.subject_code,
                    s.subject_name
                FROM attendance a
                JOIN subjects s ON a.subject_id = s.subject_id
                WHERE a.student_id = ?
                ORDER BY s.subject_code ASC
            """, (sid,)).fetchall()

            tot_obt = sum(m["marks_obtained"] for m in st_all_marks)
            tot_max = sum(m["max_marks"] for m in st_all_marks)
            avg_m = round(100.0 * tot_obt / tot_max, 2) if tot_max > 0 else None

            tot_att = sum(a["attended_classes"] for a in st_all_att)
            tot_cls = sum(a["total_classes"] for a in st_all_att)
            att_pct = round(100.0 * tot_att / tot_cls, 2) if tot_cls > 0 else None

            risk = calculate_risk(avg_m, att_pct)

            advisees_list.append({
                "assignment_id": adv["assignment_id"],
                "student_id": sid,
                "roll_number": adv["roll_number"],
                "full_name": adv["full_name"],
                "department": adv["department"],
                "year": adv["year"],
                "section": adv["section"],
                "assigned_at": adv["assigned_at"],
                "average_marks": avg_m,
                "attendance_percentage": att_pct,
                "risk_level": risk,
                "marks_count": len(st_all_marks),
                "attendance_count": len(st_all_att),
                "marks": [dict(m) for m in st_all_marks],
                "attendance": [dict(a) for a in st_all_att]
            })

        return jsonify({
            "faculty": dict(faculty),
            "assignments": [dict(row) for row in assignments],
            # students list uses enriched performance data so the frontend gets
            # risk level, avg marks, attendance % and enrolled_subjects per student.
            # Raw student rows (without risk/subject info) are kept for backward compat.
            "students": assigned_performance if assigned_performance else [dict(row) for row in students],
            "marks": [dict(row) for row in assigned_marks],
            "attendance": [dict(row) for row in assigned_attendance],
            "performance": assigned_performance,
            "advisees": advisees_list,
            "statistics": {
                "assigned_subjects": len(subject_ids),
                "assigned_students": len(student_ids),
                "marks_recorded": len(assigned_marks),
                "attendance_records": len(assigned_attendance),
                "total_advisees": len(advisees_list)
            }
        })

    except Exception as error:
        return jsonify({"error": str(error)}), 500

    finally:
        connection.close()


# --------------------------------------------------
# FACULTY DASHBOARD PAGE
# --------------------------------------------------

@app.route("/faculty")
def faculty_dashboard():
    user = get_current_user()
    if not user:
        return redirect(url_for("login_page"))
    if user["role"] == "student":
        return redirect(url_for("student_dashboard"))
    return render_template("faculty_dashboard.html", user=user)


# --------------------------------------------------
# STUDENT DASHBOARD API & PORTAL
# --------------------------------------------------

@app.route("/student/dashboard")
@app.route("/student")
def student_dashboard():
    user = get_current_user()
    if not user:
        return redirect(url_for("login_page"))

    # Security: If logged in as student, enforce their own student_id
    if user["role"] == "student":
        student_id = user.get("student_id")
        if not student_id:
            return redirect(url_for("login_page"))
    elif user["role"] in ["coordinator", "faculty"]:
        # Staff preview mode
        preview_id = request.args.get("id")
        if preview_id and preview_id.isdigit():
            student_id = int(preview_id)
        else:
            student_id = 1
    else:
        return redirect(url_for("login_page"))

    return render_template(
        "student_dashboard.html",
        user=user,
        active_student_id=student_id
    )


@app.route("/api/student/dashboard", methods=["GET"])
def get_student_dashboard_data():
    """Retrieve full academic dashboard data for the authenticated student.
    Strictly enforces session security: student ID from browser is NEVER trusted."""
    user_id = session.get("user_id")
    role = session.get("role")

    if not user_id:
        return jsonify({"error": "Authentication required. Please sign in."}), 401

    if role == "student":
        # Strictly obtain student ID from authenticated session
        student_id = session.get("student_id")
        if not student_id:
            return jsonify({"error": "Student account record not found."}), 403
    elif role in ["coordinator", "faculty"]:
        # Staff preview mode allows inspecting specific student
        try:
            student_id = int(request.args.get("id", 1))
        except (ValueError, TypeError):
            student_id = 1
    else:
        return jsonify({"error": "Unauthorized access."}), 403

    connection = get_db_connection()
    try:
        # 1. Student Profile
        student = connection.execute(
            """
            SELECT student_id, roll_number, full_name, department, year, section
            FROM students
            WHERE student_id = ?
            """,
            (student_id,)
        ).fetchone()

        if not student:
            return jsonify({"error": "Student profile not found."}), 404

        advisor_row = connection.execute(
            """
            SELECT f.faculty_id, f.full_name, f.department, f.email
            FROM class_advisor_assignments caa
            JOIN faculty f ON caa.faculty_id = f.faculty_id
            WHERE caa.student_id = ? AND caa.is_active = 1
            """,
            (student_id,)
        ).fetchone()

        # 2. Assessment marks
        marks = connection.execute(
            """
            SELECT
                m.mark_id,
                s.subject_id,
                s.subject_code,
                s.subject_name,
                m.assessment_name,
                m.marks_obtained,
                m.max_marks,
                ROUND(100.0 * m.marks_obtained / NULLIF(m.max_marks, 0), 2) AS percentage,
                m.recorded_on
            FROM marks m
            JOIN subjects s ON m.subject_id = s.subject_id
            WHERE m.student_id = ?
            ORDER BY s.subject_code ASC, m.mark_id ASC
            """,
            (student_id,)
        ).fetchall()

        # 3. Class attendance
        attendance = connection.execute(
            """
            SELECT
                a.attendance_id,
                s.subject_id,
                s.subject_code,
                s.subject_name,
                a.total_classes,
                a.attended_classes,
                ROUND(100.0 * a.attended_classes / NULLIF(a.total_classes, 0), 2) AS attendance_percentage,
                a.updated_on
            FROM attendance a
            JOIN subjects s ON a.subject_id = s.subject_id
            WHERE a.student_id = ?
            ORDER BY s.subject_code ASC
            """,
            (student_id,)
        ).fetchall()

        # 4. Aggregations & Calculations
        total_obtained = sum(m["marks_obtained"] for m in marks)
        total_maximum = sum(m["max_marks"] for m in marks)
        average_marks = round(100.0 * total_obtained / total_maximum, 2) if total_maximum > 0 else None

        total_attended = sum(a["attended_classes"] for a in attendance)
        total_classes = sum(a["total_classes"] for a in attendance)
        overall_attendance_pct = round(100.0 * total_attended / total_classes, 2) if total_classes > 0 else None

        risk_level = calculate_risk(average_marks, overall_attendance_pct)

        # Subject mapping & summary
        sub_map = {}
        for m in marks:
            sid = m["subject_id"]
            if sid not in sub_map:
                sub_map[sid] = {
                    "subject_id": sid,
                    "subject_code": m["subject_code"],
                    "subject_name": m["subject_name"],
                    "marks": [],
                    "total_obtained": 0.0,
                    "total_maximum": 0.0,
                    "attended_classes": 0,
                    "total_classes": 0,
                    "attendance_pct": None
                }
            sub_map[sid]["marks"].append(dict(m))
            sub_map[sid]["total_obtained"] += m["marks_obtained"]
            sub_map[sid]["total_maximum"] += m["max_marks"]

        for a in attendance:
            sid = a["subject_id"]
            if sid not in sub_map:
                sub_map[sid] = {
                    "subject_id": sid,
                    "subject_code": a["subject_code"],
                    "subject_name": a["subject_name"],
                    "marks": [],
                    "total_obtained": 0.0,
                    "total_maximum": 0.0,
                    "attended_classes": 0,
                    "total_classes": 0,
                    "attendance_pct": None
                }
            sub_map[sid]["attended_classes"] = a["attended_classes"]
            sub_map[sid]["total_classes"] = a["total_classes"]
            sub_map[sid]["attendance_pct"] = a["attendance_percentage"]

        subject_summary = []
        for sid, item in sub_map.items():
            item["marks_percentage"] = (
                round(100.0 * item["total_obtained"] / item["total_maximum"], 2)
                if item["total_maximum"] > 0 else None
            )
            item["subject_risk"] = calculate_risk(item["marks_percentage"], item["attendance_pct"])
            subject_summary.append(item)

        # Distinct active subjects count
        total_subjects = len(sub_map)

        # 5. Shortage Warnings & Classes Needed to Reach 75%
        shortage_warnings = []
        if overall_attendance_pct is not None:
            if overall_attendance_pct < 65:
                needed = max(0, 3 * total_classes - 4 * total_attended)
                shortage_warnings.append({
                    "level": "critical",
                    "title": "Critical Attendance Alert (< 65%)",
                    "percentage": overall_attendance_pct,
                    "threshold": 65,
                    "message": f"Your overall attendance is currently {overall_attendance_pct}%, falling below the critical 65% boundary. You are at imminent risk of exam debarment.",
                    "classes_needed_for_75": needed
                })
            elif overall_attendance_pct < 75:
                needed = max(0, 3 * total_classes - 4 * total_attended)
                shortage_warnings.append({
                    "level": "warning",
                    "title": "Attendance Shortage Warning (< 75%)",
                    "percentage": overall_attendance_pct,
                    "threshold": 75,
                    "message": f"Your overall attendance is currently {overall_attendance_pct}%, below the institutional target of 75%.",
                    "classes_needed_for_75": needed
                })

        for a in attendance:
            pct = a["attendance_percentage"]
            if pct is not None and pct < 75:
                sub_needed = max(0, 3 * a["total_classes"] - 4 * a["attended_classes"])
                shortage_warnings.append({
                    "level": "critical" if pct < 65 else "warning",
                    "title": f"Course Attendance Shortage: {a['subject_code']}",
                    "subject_code": a["subject_code"],
                    "subject_name": a["subject_name"],
                    "percentage": pct,
                    "threshold": 75,
                    "message": f"In {a['subject_code']} ({a['subject_name']}), you have attended {a['attended_classes']} out of {a['total_classes']} scheduled lectures ({pct}%).",
                    "classes_needed_for_75": sub_needed
                })

        return jsonify({
            "profile": dict(student),
            "class_advisor": dict(advisor_row) if advisor_row else None,
            "overview": {
                "average_marks": average_marks,
                "overall_attendance_pct": overall_attendance_pct,
                "risk_level": risk_level,
                "total_subjects": total_subjects,
                "total_assessments": len(marks),
                "total_classes_scheduled": total_classes,
                "total_classes_attended": total_attended
            },
            "subjects": subject_summary,
            "marks": [dict(m) for m in marks],
            "attendance": [dict(a) for a in attendance],
            "shortage_warnings": shortage_warnings
        }), 200

    finally:
        connection.close()


@app.route("/api/student/ai-insights", methods=["POST"])
def get_authenticated_student_ai_insights():
    """Secure endpoint for student AI academic insights using authenticated session."""
    user_id = session.get("user_id")
    role = session.get("role")

    if not user_id:
        return jsonify({"error": "Authentication required."}), 401

    if role == "student":
        student_id = session.get("student_id")
        if not student_id:
            return jsonify({"error": "Student account record not found."}), 403
    elif role in ["coordinator", "faculty"]:
        try:
            student_id = int(request.args.get("id", 1))
        except (ValueError, TypeError):
            student_id = 1
    else:
        return jsonify({"error": "Unauthorized access."}), 403

    return student_ai_insights(student_id)


# --------------------------------------------------
# RUN APPLICATION
# --------------------------------------------------

if __name__ == "__main__":
    app.run(
        debug=True,
        port=5002
    )
