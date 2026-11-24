#!/usr/bin/env python3
"""
Comprehensive Verification Test Suite for EduTrack Lite Authentication & RBAC Configuration
"""

import sys
import unittest
from werkzeug.security import check_password_hash
from app import app
from database import get_db_connection


class TestEduTrackLiteAuthRBAC(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        app.testing = True
        cls.client = app.test_client()

    def setUp(self):
        # Clear session before each test
        with self.client.session_transaction() as sess:
            sess.clear()

    # -------------------------------------------------------------
    # 1. DATABASE & CREDENTIAL INTEGRITY TESTS
    # -------------------------------------------------------------
    def test_01_database_accounts_and_password_hashes(self):
        """Verify coordinator, faculty, and student accounts exist with valid hashes."""
        conn = get_db_connection()
        try:
            # 1. Coordinator
            coord = conn.execute("SELECT * FROM users WHERE username = 'coordinator'").fetchone()
            self.assertIsNotNone(coord, "Coordinator user account must exist")
            self.assertEqual(coord["role"], "coordinator")
            self.assertTrue(check_password_hash(coord["password_hash"], "EduTrack@2026"))
            self.assertFalse(check_password_hash(coord["password_hash"], "wrongpassword"))

            # 2. Faculty
            fac = conn.execute("SELECT * FROM users WHERE username = 'faculty'").fetchone()
            self.assertIsNotNone(fac, "Faculty user account must exist")
            self.assertEqual(fac["role"], "faculty")
            self.assertTrue(check_password_hash(fac["password_hash"], "Faculty@2026"))
            self.assertFalse(check_password_hash(fac["password_hash"], "wrongpassword"))

            # 3. Student
            stu = conn.execute("SELECT * FROM users WHERE username = 'student'").fetchone()
            self.assertIsNotNone(stu, "Student user account must exist")
            self.assertEqual(stu["role"], "student")
            self.assertTrue(check_password_hash(stu["password_hash"], "Student@2026"))
            self.assertFalse(check_password_hash(stu["password_hash"], "wrongpassword"))

            # 4. Student account must link to a valid student record
            self.assertIsNotNone(stu["student_id"], "Student must be linked via student_id")
            linked_st = conn.execute(
                "SELECT * FROM students WHERE student_id = ?", (stu["student_id"],)
            ).fetchone()
            self.assertIsNotNone(linked_st, "Linked student record must exist in students table")

            # 5. Check uniqueness of usernames (no duplicates)
            user_counts = conn.execute(
                "SELECT username, COUNT(*) as cnt FROM users GROUP BY username HAVING cnt > 1"
            ).fetchall()
            self.assertEqual(len(user_counts), 0, "No duplicate usernames allowed in users table")
        finally:
            conn.close()

    def test_02_data_preservation(self):
        """Verify that existing students, marks, attendance, subjects, and allocations are preserved."""
        conn = get_db_connection()
        try:
            students = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
            subjects = conn.execute("SELECT COUNT(*) FROM subjects").fetchone()[0]
            marks = conn.execute("SELECT COUNT(*) FROM marks").fetchone()[0]
            attendance = conn.execute("SELECT COUNT(*) FROM attendance").fetchone()[0]
            faculty = conn.execute("SELECT COUNT(*) FROM faculty").fetchone()[0]
            assignments = conn.execute("SELECT COUNT(*) FROM faculty_assignments").fetchone()[0]

            self.assertGreaterEqual(students, 5, "All existing students must be preserved")
            self.assertGreaterEqual(subjects, 3, "All existing subjects must be preserved")
            self.assertGreaterEqual(marks, 4, "All existing marks must be preserved")
            self.assertGreaterEqual(attendance, 3, "All existing attendance records must be preserved")
            self.assertGreaterEqual(faculty, 2, "All faculty records must be preserved")
            self.assertGreaterEqual(assignments, 2, "Faculty allocations must be preserved")
        finally:
            conn.close()

    # -------------------------------------------------------------
    # 2. LOGIN AUTHENTICATION & REDIRECTION TESTS
    # -------------------------------------------------------------
    def test_03_coordinator_login_and_redirect(self):
        """Test Coordinator login redirects to Coordinator Dashboard ('/')."""
        # Form-based login
        res = self.client.post("/login", data={
            "username": "coordinator",
            "password": "EduTrack@2026"
        }, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers.get("Location"), "/")

        # JSON API login
        res_json = self.client.post("/api/auth/login", json={
            "username": "coordinator",
            "password": "EduTrack@2026"
        })
        self.assertEqual(res_json.status_code, 200)
        data = res_json.get_json()
        self.assertEqual(data["user"]["role"], "coordinator")
        self.assertEqual(data["redirect_url"], "/")

    def test_04_faculty_login_and_redirect(self):
        """Test Faculty login redirects to Faculty Dashboard ('/faculty')."""
        # Form-based login
        res = self.client.post("/login", data={
            "username": "faculty",
            "password": "Faculty@2026"
        }, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers.get("Location"), "/faculty")

        # JSON API login
        res_json = self.client.post("/api/auth/login", json={
            "username": "faculty",
            "password": "Faculty@2026"
        })
        self.assertEqual(res_json.status_code, 200)
        data = res_json.get_json()
        self.assertEqual(data["user"]["role"], "faculty")
        self.assertEqual(data["redirect_url"], "/faculty")

    def test_05_student_login_and_redirect(self):
        """Test Student login redirects to Student Dashboard ('/student')."""
        # Form-based login
        res = self.client.post("/login", data={
            "username": "student",
            "password": "Student@2026"
        }, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers.get("Location"), "/student")

        # JSON API login
        res_json = self.client.post("/api/auth/login", json={
            "username": "student",
            "password": "Student@2026"
        })
        self.assertEqual(res_json.status_code, 200)
        data = res_json.get_json()
        self.assertEqual(data["user"]["role"], "student")
        self.assertEqual(data["redirect_url"], "/student")

    # -------------------------------------------------------------
    # 3. INCORRECT PASSWORD & ERROR HANDLING TESTS
    # -------------------------------------------------------------
    def test_06_incorrect_passwords(self):
        """Test login fails with incorrect password for all three roles."""
        for user in ["coordinator", "faculty", "student"]:
            res = self.client.post("/login", data={
                "username": user,
                "password": "WrongPassword123!"
            })
            self.assertEqual(res.status_code, 200)
            self.assertIn(b"Invalid username or password", res.data)

            res_api = self.client.post("/api/auth/login", json={
                "username": user,
                "password": "WrongPassword123!"
            })
            self.assertEqual(res_api.status_code, 401)
            self.assertIn("Invalid username or password", res_api.get_json().get("error", ""))

    def test_07_invalid_or_missing_credentials(self):
        """Test non-existent username and empty input."""
        res_empty = self.client.post("/login", data={"username": "", "password": ""})
        self.assertIn(b"Please enter both username and password", res_empty.data)

        res_ghost = self.client.post("/login", data={"username": "ghost_user", "password": "any"})
        self.assertIn(b"Invalid username or password", res_ghost.data)

    # -------------------------------------------------------------
    # 4. LOGOUT & SESSION HANDLING TESTS
    # -------------------------------------------------------------
    def test_08_logout_and_session_clearing(self):
        """Test logout clears session and redirects to /login."""
        # Login first
        self.client.post("/login", data={"username": "coordinator", "password": "EduTrack@2026"})
        me_before = self.client.get("/api/auth/me").get_json()
        self.assertTrue(me_before.get("authenticated"))

        # Logout via GET
        res_logout = self.client.get("/logout", follow_redirects=False)
        self.assertEqual(res_logout.status_code, 302)
        self.assertEqual(res_logout.headers.get("Location"), "/login")

        me_after = self.client.get("/api/auth/me").get_json()
        self.assertFalse(me_after.get("authenticated"))

        # Test API logout
        self.client.post("/api/auth/login", json={"username": "faculty", "password": "Faculty@2026"})
        res_api_logout = self.client.post("/api/auth/logout")
        self.assertEqual(res_api_logout.status_code, 200)

        me_after_api = self.client.get("/api/auth/me").get_json()
        self.assertFalse(me_after_api.get("authenticated"))

    # -------------------------------------------------------------
    # 5. ROLE-BASED ACCESS CONTROL (RBAC) TESTS
    # -------------------------------------------------------------
    def test_09_unauthenticated_page_access_redirects(self):
        """Unauthenticated visits to protected portals redirect to /login."""
        for path in ["/", "/faculty", "/student", "/student-analysis"]:
            res = self.client.get(path, follow_redirects=False)
            self.assertEqual(res.status_code, 302, f"Expected 302 redirect for unauthenticated {path}")
            self.assertEqual(res.headers.get("Location"), "/login")

    def test_10_coordinator_role_page_access(self):
        """Coordinator can access Coordinator Dashboard ('/') and faculty portal."""
        self.client.post("/login", data={"username": "coordinator", "password": "EduTrack@2026"})

        # Coordinator Dashboard
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Coordinator Dashboard", res.data)

        # Faculty portal (allowed preview/review for coordinator)
        res_fac = self.client.get("/faculty")
        self.assertEqual(res_fac.status_code, 200)

    def test_11_faculty_role_page_access(self):
        """Faculty accesses Faculty Dashboard ('/faculty'); accessing '/' redirects to '/faculty'."""
        self.client.post("/login", data={"username": "faculty", "password": "Faculty@2026"})

        # Faculty Dashboard
        res = self.client.get("/faculty")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Faculty Teaching Portal", res.data)

        # Visiting '/' redirects to '/faculty'
        res_root = self.client.get("/", follow_redirects=False)
        self.assertEqual(res_root.status_code, 302)
        self.assertEqual(res_root.headers.get("Location"), "/faculty")

    def test_12_student_role_page_access_restrictions(self):
        """Student accesses '/student'; visiting '/' or '/faculty' or '/student-analysis' redirects to '/student'."""
        self.client.post("/login", data={"username": "student", "password": "Student@2026"})

        # Student Dashboard
        res_stu = self.client.get("/student")
        self.assertEqual(res_stu.status_code, 200)
        self.assertIn(b"Student Portal", res_stu.data)

        # Visiting '/' redirects to '/student'
        res_root = self.client.get("/", follow_redirects=False)
        self.assertEqual(res_root.status_code, 302)
        self.assertEqual(res_root.headers.get("Location"), "/student")

        # Visiting '/faculty' redirects to '/student'
        res_fac = self.client.get("/faculty", follow_redirects=False)
        self.assertEqual(res_fac.status_code, 302)
        self.assertEqual(res_fac.headers.get("Location"), "/student")

        # Visiting '/student-analysis' redirects to '/student'
        res_ana = self.client.get("/student-analysis", follow_redirects=False)
        self.assertEqual(res_ana.status_code, 302)
        self.assertEqual(res_ana.headers.get("Location"), "/student")

    # -------------------------------------------------------------
    # 6. STUDENT RECORD ISOLATION TESTS
    # -------------------------------------------------------------
    def test_13_student_record_isolation(self):
        """Ensure student account strictly accesses ONLY their own academic records."""
        # Login as student (linked to student_id 1)
        self.client.post("/login", data={"username": "student", "password": "Student@2026"})

        # 1. /api/student/dashboard returns own record (student_id 1)
        dash = self.client.get("/api/student/dashboard")
        self.assertEqual(dash.status_code, 200)
        dash_data = dash.get_json()
        self.assertEqual(dash_data["profile"]["student_id"], 1)

        # 2. Tampering with ?id=2 on /api/student/dashboard is IGNORED
        dash_tamper = self.client.get("/api/student/dashboard?id=2")
        self.assertEqual(dash_tamper.status_code, 200)
        self.assertEqual(dash_tamper.get_json()["profile"]["student_id"], 1)

        # 3. Direct access to own analysis API -> 200
        res_own = self.client.get("/api/students/1/analysis")
        self.assertEqual(res_own.status_code, 200)
        self.assertEqual(res_own.get_json()["student"]["student_id"], 1)

        # 4. Attempt to access other student's record (student_id 2) -> 403 Forbidden!
        res_other = self.client.get("/api/students/2/analysis")
        self.assertEqual(res_other.status_code, 403)
        self.assertIn("Access denied", res_other.get_json().get("error", ""))

        # 5. Attempt to generate AI insights for other student -> 403 Forbidden!
        res_other_ai = self.client.post("/api/students/2/ai-insights")
        self.assertEqual(res_other_ai.status_code, 403)

        # 6. Student cannot access cohort performance list -> 403 Forbidden!
        res_perf = self.client.get("/api/performance")
        self.assertEqual(res_perf.status_code, 403)

        # 7. Student cannot access faculty dashboard data -> 403 Forbidden!
        res_fac_data = self.client.get("/api/faculty/0/dashboard")
        self.assertEqual(res_fac_data.status_code, 403)

        # 8. Student cannot modify administrative data
        res_mod = self.client.post("/api/students", json={
            "roll_number": "999", "full_name": "Hacker", "department": "CSE", "year": 1
        })
        self.assertEqual(res_mod.status_code, 403)

    # -------------------------------------------------------------
    # 7. DASHBOARD DATA & APIS TESTS
    # -------------------------------------------------------------
    def test_14_coordinator_dashboard_apis(self):
        """Verify Coordinator Dashboard APIs function correctly when authenticated."""
        self.client.post("/login", data={"username": "coordinator", "password": "EduTrack@2026"})

        # Performance API
        perf = self.client.get("/api/performance")
        self.assertEqual(perf.status_code, 200)
        self.assertIsInstance(perf.get_json(), list)

        # Students API
        students = self.client.get("/api/students")
        self.assertEqual(students.status_code, 200)
        self.assertGreaterEqual(len(students.get_json()), 5)

        # Subjects API
        subjects = self.client.get("/api/subjects")
        self.assertEqual(subjects.status_code, 200)
        self.assertGreaterEqual(len(subjects.get_json()), 3)

        # Faculty API
        faculty = self.client.get("/api/faculty")
        self.assertEqual(faculty.status_code, 200)
        self.assertGreaterEqual(len(faculty.get_json()), 2)

    def test_15_faculty_dashboard_api(self):
        """Verify Faculty Dashboard API returns teaching assignments and enrolled roster."""
        self.client.post("/login", data={"username": "faculty", "password": "Faculty@2026"})

        fac_dash = self.client.get("/api/faculty/0/dashboard")
        self.assertEqual(fac_dash.status_code, 200)
        data = fac_dash.get_json()

        self.assertIn("faculty", data)
        self.assertIn("assignments", data)
        self.assertIn("students", data)
        self.assertIn("statistics", data)
        self.assertGreaterEqual(len(data["assignments"]), 1)
        self.assertGreaterEqual(len(data["students"]), 1)

    def test_16_student_dashboard_api(self):
        """Verify Student Dashboard API returns profile, overview, subjects, marks, and attendance."""
        self.client.post("/login", data={"username": "student", "password": "Student@2026"})

        stu_dash = self.client.get("/api/student/dashboard")
        self.assertEqual(stu_dash.status_code, 200)
        data = stu_dash.get_json()

        self.assertIn("profile", data)
        self.assertIn("overview", data)
        self.assertIn("subjects", data)
        self.assertIn("marks", data)
        self.assertIn("attendance", data)
        self.assertIn("shortage_warnings", data)
        self.assertEqual(data["profile"]["roll_number"], "01")


if __name__ == "__main__":
    unittest.main(verbosity=2)
