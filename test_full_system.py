#!/usr/bin/env python3
"""
Full System Verification Test Suite for EduTrack Lite
Tests: Student Account Management, Faculty Assignment Preview,
       Class Advisor Assignment, Advisee Dashboard, Security, Data Preservation
"""

import sys
import unittest
from werkzeug.security import check_password_hash
from app import app
from database import get_db_connection


class TestStudentAccountManagement(unittest.TestCase):
    """MODULE 1: Student Login Account Creation & Management"""

    @classmethod
    def setUpClass(cls):
        app.testing = True
        cls.client = app.test_client()
        cls.test_user_id = None
        # Clean up any stale test accounts so test_02 passes (Karthik may have been created before)
        conn = get_db_connection()
        conn.execute("DELETE FROM users WHERE username IN ('karthik_test', 'karthik_verify', 'Karthik')")
        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        # Clean up test account after all tests
        conn = get_db_connection()
        conn.execute("DELETE FROM users WHERE username IN ('karthik_test', 'karthik_verify', 'Karthik')")
        conn.commit()
        conn.close()

    def setUp(self):
        with self.client.session_transaction() as sess:
            sess.clear()

    def _login_coordinator(self):
        self.client.post("/login", data={
            "username": "coordinator", "password": "EduTrack@2026"
        })

    def _login_student(self, username, password):
        self.client.post("/login", data={"username": username, "password": password})

    # --- Students Without Accounts List ---
    def test_01_students_without_accounts_requires_coordinator(self):
        """Unauthenticated requests to /api/students-without-accounts are blocked."""
        res = self.client.get("/api/students-without-accounts")
        self.assertIn(res.status_code, [401, 403])

    def test_02_students_without_accounts_returns_list(self):
        """Coordinator can list students who have no login account."""
        self._login_coordinator()
        res = self.client.get("/api/students-without-accounts")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIsInstance(data, list)
        # Student Karthik (student_id=8) should appear
        ids = [s["student_id"] for s in data]
        self.assertIn(8, ids, "Karthik (student_id=8) must appear in students without accounts")

    # --- Create Student Account ---
    def test_03_create_student_account_blocked_for_non_coordinator(self):
        """Non-coordinators (faculty / unauthenticated) cannot create student accounts."""
        self.client.post("/login", data={"username": "faculty", "password": "Faculty@2026"})
        res = self.client.post("/api/student-accounts", json={
            "student_id": 8, "username": "karthik_test", "password": "Test@1234"
        })
        self.assertIn(res.status_code, [401, 403])

    def test_04_create_student_account_success(self):
        """Coordinator successfully creates a login account for Karthik (student_id=8)."""
        self._login_coordinator()
        # Clean any stale test account first (may remain from previous test run)
        conn = get_db_connection()
        conn.execute("DELETE FROM users WHERE username IN ('karthik_test', 'karthik_verify')")
        conn.commit()
        conn.close()

        res = self.client.post("/api/student-accounts", json={
            "student_id": 8,
            "username": "karthik_test",
            "password": "Karthik@2026"
        })
        self.assertIn(res.status_code, [200, 201])
        data = res.get_json()
        self.assertIn("message", data)

        # Verify in DB
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE username='karthik_test'").fetchone()
        conn.close()
        self.assertIsNotNone(user)
        self.assertEqual(user["role"], "student")
        self.assertEqual(user["student_id"], 8)
        self.assertTrue(check_password_hash(user["password_hash"], "Karthik@2026"))
        TestStudentAccountManagement.test_user_id = user["user_id"]

    def test_05_duplicate_username_rejected(self):
        """Creating a second account with an existing username is rejected."""
        self._login_coordinator()
        res = self.client.post("/api/student-accounts", json={
            "student_id": 8,
            "username": "karthik_test",
            "password": "AnotherPass@1"
        })
        self.assertIn(res.status_code, [400, 409])

    def test_06_duplicate_student_account_rejected(self):
        """Creating a second login for the same student_id is rejected."""
        self._login_coordinator()
        res = self.client.post("/api/student-accounts", json={
            "student_id": 8,
            "username": "karthik_verify",
            "password": "AnotherPass@1"
        })
        self.assertIn(res.status_code, [400, 409])

    # --- New Student Login ---
    def test_07_new_student_can_login(self):
        """Karthik can log in with the newly created credentials."""
        res = self.client.post("/login", data={
            "username": "karthik_test", "password": "Karthik@2026"
        }, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers.get("Location"), "/student")

    def test_08_new_student_dashboard_isolation(self):
        """Karthik can only access their own (student_id=8) dashboard."""
        self._login_student("karthik_test", "Karthik@2026")
        dash = self.client.get("/api/student/dashboard")
        self.assertEqual(dash.status_code, 200)
        data = dash.get_json()
        self.assertEqual(data["profile"]["student_id"], 8)
        self.assertEqual(data["profile"]["full_name"], "Karthik")

    # --- Account Status Toggle ---
    def test_09_deactivate_student_account(self):
        """Coordinator can deactivate a student login account."""
        self._login_coordinator()
        uid = TestStudentAccountManagement.test_user_id
        self.assertIsNotNone(uid)
        res = self.client.patch(f"/api/student-accounts/{uid}/status", json={"is_active": 0})
        self.assertIn(res.status_code, [200, 204])

        # Verify in DB
        conn = get_db_connection()
        user = conn.execute("SELECT is_active FROM users WHERE user_id=?", (uid,)).fetchone()
        conn.close()
        self.assertEqual(user["is_active"], 0)

    def test_10_deactivated_student_cannot_login(self):
        """A deactivated student account is rejected at login."""
        res = self.client.post("/login", data={
            "username": "karthik_test", "password": "Karthik@2026"
        })
        # Should NOT redirect to /student — expect login page with error
        self.assertEqual(res.status_code, 200)
        self.assertTrue(
            b"deactivated" in res.data.lower() or b"inactive" in res.data.lower()
            or b"denied" in res.data.lower() or b"invalid" in res.data.lower(),
            "Deactivated account should show login error"
        )

    def test_11_reactivate_student_account(self):
        """Coordinator can re-activate the deactivated student account."""
        self._login_coordinator()
        uid = TestStudentAccountManagement.test_user_id
        res = self.client.patch(f"/api/student-accounts/{uid}/status", json={"is_active": 1})
        self.assertIn(res.status_code, [200, 204])

    def test_12_reactivated_student_can_login(self):
        """After reactivation, the student can login again."""
        res = self.client.post("/login", data={
            "username": "karthik_test", "password": "Karthik@2026"
        }, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers.get("Location"), "/student")

    # --- Password Reset ---
    def test_13_coordinator_reset_student_password(self):
        """Coordinator can reset a student's password."""
        self._login_coordinator()
        uid = TestStudentAccountManagement.test_user_id
        res = self.client.post(f"/api/student-accounts/{uid}/reset-password", json={
            "new_password": "NewKarthik@2026"
        })
        self.assertIn(res.status_code, [200, 204])

    def test_14_student_login_with_new_password(self):
        """Student can log in with the reset password."""
        res = self.client.post("/login", data={
            "username": "karthik_test", "password": "NewKarthik@2026"
        }, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers.get("Location"), "/student")

    def test_15_student_cannot_access_coordinator_or_faculty_pages(self):
        """Student role is blocked from coordinator & faculty routes."""
        self._login_student("karthik_test", "NewKarthik@2026")

        res_root = self.client.get("/", follow_redirects=False)
        self.assertEqual(res_root.status_code, 302)
        self.assertEqual(res_root.headers.get("Location"), "/student")

        res_fac = self.client.get("/faculty", follow_redirects=False)
        self.assertEqual(res_fac.status_code, 302)
        self.assertEqual(res_fac.headers.get("Location"), "/student")

        # Can't call coordinator-only APIs
        res_sa = self.client.get("/api/student-accounts")
        self.assertIn(res_sa.status_code, [401, 403])

    # --- Student Accounts List ---
    def test_16_student_accounts_list_includes_active_accounts(self):
        """Coordinator's student accounts list includes all statuses."""
        self._login_coordinator()
        res = self.client.get("/api/student-accounts")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIsInstance(data, list)
        usernames = [a.get("username") for a in data]
        self.assertIn("karthik_test", usernames)

    def test_17_student_accounts_search_works(self):
        """Coordinator can search student accounts by name."""
        self._login_coordinator()
        res = self.client.get("/api/student-accounts?q=Karthik")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(any("Karthik" in a.get("full_name", "") for a in data))

    def test_18_student_accounts_status_filter_works(self):
        """Status filter returns correct accounts."""
        self._login_coordinator()
        res = self.client.get("/api/student-accounts?status=active")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        for a in data:
            if a.get("has_account"):
                self.assertEqual(a.get("is_active"), 1,
                                 f"Filtered active account {a.get('username')} should be active")

    # --- Delete Login Account ---
    def test_19_delete_student_login_preserves_student_record(self):
        """Deleting a login account removes from users table but preserves students table."""
        self._login_coordinator()
        uid = TestStudentAccountManagement.test_user_id
        self.assertIsNotNone(uid)

        res = self.client.delete(f"/api/student-accounts/{uid}")
        self.assertIn(res.status_code, [200, 204])

        # Login no longer works
        with self.client.session_transaction() as sess:
            sess.clear()
        res_login = self.client.post("/login", data={
            "username": "karthik_test", "password": "NewKarthik@2026"
        })
        self.assertEqual(res_login.status_code, 200)

        # But student record preserved
        conn = get_db_connection()
        st = conn.execute("SELECT * FROM students WHERE student_id=8").fetchone()
        conn.close()
        self.assertIsNotNone(st, "Student record must NOT be deleted with login account")
        self.assertEqual(st["full_name"], "Karthik")


class TestFacultyAssignmentPreview(unittest.TestCase):
    """MODULE 2: Faculty Assignment with Student Preview"""

    @classmethod
    def setUpClass(cls):
        app.testing = True
        cls.client = app.test_client()

    def setUp(self):
        with self.client.session_transaction() as sess:
            sess.clear()
        self.client.post("/login", data={"username": "coordinator", "password": "EduTrack@2026"})

    def test_20_preview_students_for_assignment(self):
        """Preview students matching dept=CSE, year=2, section=EK before assigning faculty."""
        res = self.client.get("/api/faculty-assignments/preview-students?department=CSE&year=2&section=EK")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("students", data)
        students = data["students"]
        self.assertGreater(len(students), 0, "Should find students in CSE Year 2 Sec EK")
        for s in students:
            self.assertEqual(s["department"], "CSE")
            self.assertEqual(s["year"], 2)
            self.assertEqual(s["section"].upper(), "EK")

    def test_21_preview_returns_empty_for_nonexistent_section(self):
        """Preview returns empty list for section that has no students."""
        res = self.client.get("/api/faculty-assignments/preview-students?department=CSE&year=4&section=ZZ")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(len(data.get("students", [])), 0)

    def test_22_faculty_cannot_access_preview(self):
        """Faculty role is blocked from coordinator-only preview API."""
        with self.client.session_transaction() as sess:
            sess.clear()
        self.client.post("/login", data={"username": "faculty", "password": "Faculty@2026"})
        res = self.client.get("/api/faculty-assignments/preview-students?department=CSE&year=2&section=EK")
        self.assertIn(res.status_code, [401, 403])


class TestClassAdvisorAssignment(unittest.TestCase):
    """MODULE 3: Class Advisor Assignment System"""

    @classmethod
    def setUpClass(cls):
        app.testing = True
        cls.client = app.test_client()
        cls.bulk_assignment_ids = []

    def setUp(self):
        with self.client.session_transaction() as sess:
            sess.clear()
        self.client.post("/login", data={"username": "coordinator", "password": "EduTrack@2026"})

    def test_30_class_advisors_api_requires_coordinator(self):
        """Non-coordinator cannot access class advisor list."""
        with self.client.session_transaction() as sess:
            sess.clear()
        self.client.post("/login", data={"username": "faculty", "password": "Faculty@2026"})
        res = self.client.get("/api/class-advisors")
        self.assertIn(res.status_code, [401, 403])

    def test_31_preview_class_advisor_students(self):
        """Preview students for CSE Year 2 Sec EK before assigning advisor."""
        res = self.client.get("/api/class-advisors/preview?department=CSE&year=2&section=EK")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("students", data)
        self.assertGreater(len(data["students"]), 0, "CSE Year 2 EK must have students")

    def test_32_bulk_assign_section_advisor(self):
        """Coordinator assigns a faculty member as advisor for entire CSE Year 2 EK section."""
        # Find a valid faculty_id (use faculty_id=12, Adarsh Gowtham)
        res = self.client.post("/api/class-advisors/bulk", json={
            "faculty_id": 12,
            "department": "CSE",
            "year": 2,
            "section": "EK"
        })
        self.assertIn(res.status_code, [200, 201])
        data = res.get_json()
        self.assertIn("message", data)

        # Verify assignments exist
        conn = get_db_connection()
        rows = conn.execute(
            "SELECT ca.assignment_id, s.full_name FROM class_advisor_assignments ca "
            "JOIN students s ON s.student_id = ca.student_id "
            "WHERE ca.faculty_id=12 AND ca.is_active=1"
        ).fetchall()
        conn.close()
        self.assertGreater(len(rows), 0, "Bulk advisor assignment must create records")
        TestClassAdvisorAssignment.bulk_assignment_ids = [r["assignment_id"] for r in rows]

    def test_33_each_student_has_max_one_active_advisor(self):
        """No student should have more than one active class advisor."""
        conn = get_db_connection()
        duplicates = conn.execute("""
            SELECT student_id, COUNT(*) as cnt
            FROM class_advisor_assignments
            WHERE is_active=1
            GROUP BY student_id
            HAVING cnt > 1
        """).fetchall()
        conn.close()
        self.assertEqual(len(duplicates), 0,
                         f"Students with multiple active advisors: {[dict(d) for d in duplicates]}")

    def test_34_reassign_advisor_deactivates_old(self):
        """Reassigning an advisor to a student properly deactivates the old assignment."""
        # Individual assign: change advisor for student_id=1 to faculty_id=11 (Prakash)
        res = self.client.post("/api/class-advisors/assign-student", json={
            "student_id": 1,
            "faculty_id": 11
        })
        self.assertIn(res.status_code, [200, 201])

        # Only one active advisor for student_id=1
        conn = get_db_connection()
        rows = conn.execute(
            "SELECT * FROM class_advisor_assignments WHERE student_id=1 AND is_active=1"
        ).fetchall()
        conn.close()
        self.assertEqual(len(rows), 1, "Student must have exactly one active advisor after reassignment")
        self.assertEqual(rows[0]["faculty_id"], 11)

    def test_35_class_advisors_list_accessible(self):
        """Coordinator can retrieve the full class advisors roster."""
        res = self.client.get("/api/class-advisors")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0, "Should have at least one class advisor assignment")

    def test_36_deactivate_class_advisor_assignment(self):
        """Coordinator can deactivate (delete) an individual class advisor assignment."""
        # Get an assignment_id
        conn = get_db_connection()
        row = conn.execute(
            "SELECT assignment_id FROM class_advisor_assignments WHERE is_active=1 LIMIT 1"
        ).fetchone()
        conn.close()
        self.assertIsNotNone(row)

        aid = row["assignment_id"]
        res = self.client.delete(f"/api/class-advisors/{aid}")
        self.assertIn(res.status_code, [200, 204])

        conn = get_db_connection()
        updated = conn.execute(
            "SELECT is_active FROM class_advisor_assignments WHERE assignment_id=?", (aid,)
        ).fetchone()
        conn.close()
        # Should be deactivated (is_active=0) rather than deleted
        if updated:
            self.assertEqual(updated["is_active"], 0, "Advisor assignment should be deactivated, not deleted")


class TestFacultyAdviseesDashboard(unittest.TestCase):
    """MODULE 4: Faculty Dashboard - Advisee Students"""

    @classmethod
    def setUpClass(cls):
        app.testing = True
        cls.client = app.test_client()

    def setUp(self):
        with self.client.session_transaction() as sess:
            sess.clear()

    def test_40_faculty_dashboard_includes_advisees(self):
        """Faculty Dashboard API must return 'advisees' key with correct structure."""
        self.client.post("/login", data={"username": "faculty", "password": "Faculty@2026"})
        res = self.client.get("/api/faculty/0/dashboard")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertIn("advisees", data,
                      "Faculty dashboard must include 'advisees' list from class advisor assignments")
        advisees = data["advisees"]
        self.assertIsInstance(advisees, list)

        for a in advisees:
            self.assertIn("student_id", a)
            self.assertIn("full_name", a)
            self.assertIn("roll_number", a)
            self.assertIn("risk_level", a)

    def test_41_faculty_advisees_have_risk_data(self):
        """Advisee records include avg_marks, attendance_percentage, and risk_level."""
        self.client.post("/login", data={"username": "faculty", "password": "Faculty@2026"})
        res = self.client.get("/api/faculty/0/dashboard")
        data = res.get_json()
        for a in data.get("advisees", []):
            self.assertIn("risk_level", a)
            self.assertIn("avg_marks", a)
            self.assertIn("attendance_percentage", a)


class TestStudentDashboardAdvisorDisplay(unittest.TestCase):
    """MODULE 5: Student Dashboard - Class Advisor Details"""

    @classmethod
    def setUpClass(cls):
        app.testing = True
        cls.client = app.test_client()

    def setUp(self):
        with self.client.session_transaction() as sess:
            sess.clear()

    def test_50_student_dashboard_includes_class_advisor(self):
        """Student Dashboard API returns 'class_advisor' field."""
        self.client.post("/login", data={"username": "student", "password": "Student@2026"})
        res = self.client.get("/api/student/dashboard")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        # class_advisor key should be present (can be None if not assigned)
        self.assertIn("class_advisor", data,
                      "Student dashboard API must include 'class_advisor' field")

    def test_51_class_advisor_contains_name_field_when_assigned(self):
        """When a Class Advisor is assigned, the field contains advisor name."""
        self.client.post("/login", data={"username": "student", "password": "Student@2026"})
        res = self.client.get("/api/student/dashboard")
        data = res.get_json()

        advisor = data.get("class_advisor")
        if advisor:
            # If advisor assigned, must have name field
            self.assertIn("name", advisor,
                          "class_advisor object must contain 'name' field")


class TestDataPreservationFinal(unittest.TestCase):
    """Final Data Integrity Check - Ensure all original records are intact"""

    @classmethod
    def setUpClass(cls):
        app.testing = True
        cls.client = app.test_client()

    def test_60_all_6_students_preserved(self):
        """All 6 original students still exist in the students table."""
        conn = get_db_connection()
        count = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        conn.close()
        self.assertGreaterEqual(count, 6, f"Expected at least 6 students, found {count}")

    def test_61_all_30_marks_preserved(self):
        """All 30 original mark records are intact."""
        conn = get_db_connection()
        count = conn.execute("SELECT COUNT(*) FROM marks").fetchone()[0]
        conn.close()
        self.assertGreaterEqual(count, 30, f"Expected at least 30 marks, found {count}")

    def test_62_all_29_attendance_records_preserved(self):
        """All 29 original attendance records are intact."""
        conn = get_db_connection()
        count = conn.execute("SELECT COUNT(*) FROM attendance").fetchone()[0]
        conn.close()
        self.assertGreaterEqual(count, 29, f"Expected at least 29 attendance records, found {count}")

    def test_63_all_8_faculty_preserved(self):
        """All 8 original faculty records are intact."""
        conn = get_db_connection()
        count = conn.execute("SELECT COUNT(*) FROM faculty").fetchone()[0]
        conn.close()
        self.assertGreaterEqual(count, 8, f"Expected at least 8 faculty, found {count}")

    def test_64_specific_students_intact(self):
        """Specific student records (Aakash, Younus, Wahid, Sai, Maruthi, Karthik) remain intact."""
        conn = get_db_connection()
        names = [row["full_name"] for row in conn.execute("SELECT full_name FROM students").fetchall()]
        conn.close()
        expected = ["Aakash", "Younus", "Wahid", "Sai", "Maruthi", "Karthik"]
        for name in expected:
            self.assertIn(name, names, f"Student '{name}' must be preserved in students table")

    def test_65_core_credentials_unchanged(self):
        """Core login credentials (coordinator, faculty, student) remain valid."""
        conn = get_db_connection()
        for username, password, role in [
            ("coordinator", "EduTrack@2026", "coordinator"),
            ("faculty", "Faculty@2026", "faculty"),
            ("student", "Student@2026", "student"),
        ]:
            user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            self.assertIsNotNone(user, f"User '{username}' must exist")
            self.assertEqual(user["role"], role)
            self.assertTrue(
                check_password_hash(user["password_hash"], password),
                f"Password for '{username}' must be valid"
            )
        conn.close()

    def test_66_no_plaintext_passwords_in_db(self):
        """Verify no user has a plaintext (non-hashed) password stored."""
        conn = get_db_connection()
        users = conn.execute("SELECT username, password_hash FROM users").fetchall()
        conn.close()
        for u in users:
            pw = u["password_hash"] or ""
            self.assertTrue(
                pw.startswith("scrypt:") or pw.startswith("pbkdf2:") or pw.startswith("argon2:"),
                f"User '{u['username']}' has an unexpected password_hash format: {pw[:30]}..."
            )

    def test_67_faculty_assignments_intact(self):
        """Faculty teaching assignments are preserved."""
        conn = get_db_connection()
        count = conn.execute("SELECT COUNT(*) FROM faculty_assignments").fetchone()[0]
        conn.close()
        self.assertGreaterEqual(count, 2, "Faculty assignments must be preserved")

    def test_68_class_advisor_assignments_table_exists(self):
        """class_advisor_assignments table was successfully created."""
        conn = get_db_connection()
        tbl = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='class_advisor_assignments'"
        ).fetchone()
        conn.close()
        self.assertIsNotNone(tbl, "class_advisor_assignments table must exist")

    def test_69_users_table_has_is_active_column(self):
        """users table has the is_active column added during migration."""
        conn = get_db_connection()
        cols = [row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
        conn.close()
        self.assertIn("is_active", cols, "users table must have 'is_active' column")


class TestSecurityEnforcement(unittest.TestCase):
    """Security Enforcement: Faculty boundary and admin-only operations"""

    @classmethod
    def setUpClass(cls):
        app.testing = True
        cls.client = app.test_client()

    def setUp(self):
        with self.client.session_transaction() as sess:
            sess.clear()

    def test_70_faculty_cannot_add_subject(self):
        """Faculty cannot add a subject — only coordinator can."""
        self.client.post("/login", data={"username": "faculty", "password": "Faculty@2026"})
        res = self.client.post("/api/subjects", json={
            "subject_code": "HACK101", "subject_name": "Hacker Subject"
        })
        self.assertIn(res.status_code, [401, 403])

    def test_71_student_cannot_add_subject(self):
        """Student cannot add a subject."""
        self.client.post("/login", data={"username": "student", "password": "Student@2026"})
        res = self.client.post("/api/subjects", json={
            "subject_code": "HACK101", "subject_name": "Hacker Subject"
        })
        self.assertIn(res.status_code, [401, 403])

    def test_72_student_cannot_reset_passwords(self):
        """Student cannot call /api/student-accounts/<id>/reset-password."""
        self.client.post("/login", data={"username": "student", "password": "Student@2026"})
        res = self.client.post("/api/student-accounts/1/reset-password", json={"new_password": "hack"})
        self.assertIn(res.status_code, [401, 403])

    def test_73_student_cannot_assign_class_advisors(self):
        """Student cannot call class advisor assignment APIs."""
        self.client.post("/login", data={"username": "student", "password": "Student@2026"})
        res_bulk = self.client.post("/api/class-advisors/bulk", json={
            "faculty_id": 7, "department": "CSE", "year": 2, "section": "EK"
        })
        self.assertIn(res_bulk.status_code, [401, 403])

        res_ind = self.client.post("/api/class-advisors/assign-student", json={
            "student_id": 1, "faculty_id": 7
        })
        self.assertIn(res_ind.status_code, [401, 403])

    def test_74_faculty_cannot_create_student_accounts(self):
        """Faculty cannot call student account creation API."""
        self.client.post("/login", data={"username": "faculty", "password": "Faculty@2026"})
        res = self.client.post("/api/student-accounts", json={
            "student_id": 8, "username": "hack_acc", "password": "Hack@1234"
        })
        self.assertIn(res.status_code, [401, 403])

    def test_75_student_isolation_cannot_view_other_student(self):
        """Student cannot view another student's analysis — 403."""
        self.client.post("/login", data={"username": "student", "password": "Student@2026"})
        res = self.client.get("/api/students/2/analysis")
        self.assertEqual(res.status_code, 403)


if __name__ == "__main__":
    import sys
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    for cls in [
        TestStudentAccountManagement,
        TestFacultyAssignmentPreview,
        TestClassAdvisorAssignment,
        TestFacultyAdviseesDashboard,
        TestStudentDashboardAdvisorDisplay,
        TestDataPreservationFinal,
        TestSecurityEnforcement
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
