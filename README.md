# EduTrack Lite - Student Academic Performance & Risk Analysis System

**EduTrack Lite** is a comprehensive, full-stack college management and student academic analysis platform built with **Python Flask**, **SQLite3**, **HTML5/CSS3**, **vanilla JavaScript**, **Chart.js**, and **local Ollama AI integration**.

The system provides end-to-end management for academic coordinators and faculty members, combining automated academic risk detection, strict academic data protection, and personalized local AI-driven student recommendations.

---

## Table of Contents
1. [Key Features](#key-features)
2. [Tech Stack](#tech-stack)
3. [System Architecture & Database Schema](#system-architecture--database-schema)
4. [Academic Risk Classification Rules](#academic-risk-classification-rules)
5. [Installation & Setup](#installation--setup)
6. [Default Login Credentials](#default-login-credentials)
7. [Running the Application](#running-the-application)
8. [Module-by-Module Documentation](#module-by-module-documentation)
9. [AI Integration & Fallback Engine](#ai-integration--fallback-engine)
10. [Test Suite & Verification Results](#test-suite--verification-results)
11. [Project File Structure & Inventory](#project-file-structure--inventory)

---

## Key Features

- **Authentication & Role-Based Portals**:
  - Dedicated **Coordinator Workspace** for full academic administration, curriculum governance, faculty allocations, student account management, and class advisor assignments.
  - Dedicated **Faculty Portal** for assigned course rosters, assessment entry, class attendance updates, at-risk student watchlists, and advisee management.
  - Dedicated **Student Dashboard & AI Insights** for authenticated student profile view, assessment history, class attendance, class advisor details, and personalized academic insights with strict record isolation.
- **Student Management**: Full CRUD with roll number uniqueness, multi-department filtering, real-time search, and edit/delete modals.
- **Student Login Account Management**: Coordinator creates login accounts for existing students. Activate/deactivate, reset passwords, and prevent duplicate accounts per student.
- **Subject Management**: Full CRUD with subject code uniqueness, edit modals, and strict dependency protection against accidental deletion.
- **Marks Management**: Assessment recording, real-time percentage calculations, range validations, and edit/delete modals.
- **Attendance Management**: Class attendance recording, percentage computation, validation, and edit/delete modals.
- **Faculty Management & Teaching Allocations**: Register faculty members, allocate teaching assignments by course, academic year, and section with live student preview before confirming.
- **Class Advisor Assignment**: Assign a Class Advisor (faculty) to a whole section or individual student. One active advisor per student enforced at database level. Bulk section-level and individual assignment with live preview.
- **Faculty Advisees Management**: Faculty can view and manage their assigned advisees with risk badges and mentorship links.
- **Dynamic Coordinator Dashboard**: Real-time KPI statistic cards and interactive Chart.js visualizations.
- **AI-Powered Student Insights**: Personalized local AI academic analysis powered by **Ollama (`qwen3.5:4b`)**, featuring a local Academic Heuristic Rule Engine as a 100% reliable fallback.
- **Strict Academic Protection**: Deletion of students or subjects with existing academic history is strictly prevented by both backend foreign key constraints and frontend dependency verifications.

---

## Tech Stack

| Component | Technology | Description |
| :--- | :--- | :--- |
| **Backend Framework** | Python 3.15 / Flask 3.1.3 | Lightweight, robust WSGI web server and REST API |
| **Database** | SQLite 3 | Relational database with strict `PRAGMA foreign_keys = ON` |
| **Authentication** | Werkzeug Security | Secure password hashing (`scrypt`) and session management |
| **Frontend UI** | HTML5, CSS3 | Custom earthy green academic theme, responsive desktop/mobile |
| **Client Scripting** | Vanilla JavaScript (ES6+) | Clean async/await fetch API, zero heavy framework dependencies |
| **Visualizations** | Chart.js | Dynamic doughnut and bar charts for risk & department breakdown |
| **AI Integration** | Ollama (`qwen3.5:4b`) | Privacy-first local LLM inference via REST API (`/api/chat`) |

---

## System Architecture & Database Schema

The database `edutrack.db` enforces relational integrity and check constraints across **9 core entities**:

```
+------------------------------------------------------------------------------------+
|                                    USERS                                           |
| (user_id PK, username UNIQUE, password_hash, role [coordinator|faculty|student],   |
|  student_id FK -> students, is_active)                                             |
+--------------------------+---------------------------------+-----------------------+
                           | 1:1                             | 1:1
                           v                                 v
+--------------------------------------+   +-----------------------------------------+
|               FACULTY                |   |                STUDENTS                 |
| (faculty_id PK, user_id FK UNIQUE,   |   | (student_id PK, roll_number UNIQUE,     |
|  full_name, department, email UNIQUE)|   |  full_name, department, year, section)  |
+------------------+-------------------+   +----+--------------------+---------------+
                   | 1:N                        | 1:N                 | 1:N
                   v                            v                     v
+--------------------------------------+   +-----------+         +-------------------+
|         FACULTY_ASSIGNMENTS          |   |   MARKS   |         |    ATTENDANCE     |
| (assignment_id PK, faculty_id FK,    |   | (mark_id, |         | (attendance_id,   |
|  subject_id FK, year, section,       |   |  student, |         |  student, subject,|
|  UNIQUE(faculty, subject, yr, sec))  |   |  subject, |         |  total, attended, |
+------------------+-------------------+   |  obtained,|         |  UNIQUE(st, sub)) |
                   | N:1                   |  max_marks|         +---------+---------+
                   v                       +-----+-----+                   | N:1
+------------------------------------------------+                         |
|                                    SUBJECTS                                        |
| (subject_id PK, subject_code UNIQUE, subject_name)                                 |
+------------------------------------------------------------------------------------+

+------------------------------------------------------------------------------------+
|                         CLASS_ADVISOR_ASSIGNMENTS                                  |
| (assignment_id PK, faculty_id FK -> faculty, student_id FK -> students,            |
|  assigned_at, is_active)                                                           |
| UNIQUE INDEX on (student_id) WHERE is_active=1  [one active advisor per student]   |
+------------------------------------------------------------------------------------+
```

### Table Specifications:
1. `students`: Stores student demographic records (`roll_number`, `full_name`, `department`, `year`, `section`).
2. `users`: Stores user credentials and role (`coordinator`, `faculty`, `student`). `is_active` flag controls account status.
3. `faculty`: Links user accounts to faculty details (`full_name`, `department`, `email`).
4. `subjects`: Master course catalog (`subject_code`, `subject_name`).
5. `faculty_assignments`: Maps faculty to specific subject, academic year, and section.
6. `marks`: Stores individual assessment scores (`marks_obtained`, `max_marks`, `assessment_name`, `recorded_on`).
7. `attendance`: Stores aggregated class attendance (`total_classes`, `attended_classes`, `updated_on`) with unique constraint on `(student_id, subject_id)`.
8. `class_advisor_assignments`: Maps one active Class Advisor (faculty) per student. Partial unique index enforces the one-active-advisor constraint at the database level.

---

## Academic Risk Classification Rules

The application uses standard academic risk rules to classify every student based on their recorded metrics:

$$\text{Average Marks (\%)} = \frac{\sum \text{Marks Obtained}}{\sum \text{Max Marks}} \times 100$$

$$\text{Attendance Percentage (\%)} = \frac{\sum \text{Classes Attended}}{\sum \text{Total Classes}} \times 100$$

| Risk Tier | Condition Criteria | Action Required |
| :--- | :--- | :--- |
| **High Risk** | Average Marks $< 40\%$ **OR** Attendance $< 65\%$ | Immediate academic counseling & remedial intervention |
| **Medium Risk** | Average Marks $< 60\%$ **OR** Attendance $< 75\%$ | Faculty monitoring & attendance improvement notice |
| **Low Risk** | Average Marks $\ge 60\%$ **AND** Attendance $\ge 75\%$ | Good academic standing; maintain performance |
| **Insufficient Data** | Missing marks records **OR** missing attendance records | Assessment or attendance entries required |

---

## Installation & Setup

### Prerequisites
- Python 3.10+ (tested on Python 3.15)
- pip package manager
- (Optional for live local AI) [Ollama](https://ollama.com/) with model `qwen3.5:4b`

### 1. Clone or Open the Repository
```bash
cd /Users/aakash/Desktop/EduTrack-Lite
```

### 2. Activate Python Virtual Environment
```bash
# On macOS / Linux:
source .venv/bin/activate

# Or create a new virtual environment if needed:
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Verify Database Initialization
The database `edutrack.db` initializes automatically on application startup. You can also run:
```bash
python3 database.py
```
*Note: Existing student records, marks, and attendance data are preserved safely.*

---

## Default Login Credentials

EduTrack Lite includes pre-configured credentials for all three portals:

| Portal | Role | Username | Password | Access & Dashboard |
| :--- | :--- | :--- | :--- | :--- |
| **Coordinator Workspace** | `coordinator` | `coordinator` | `EduTrack@2026` | Full academic administration, faculty allocations, student & subject management, student account management, class advisor assignments (`/`) |
| **Faculty Portal** | `faculty` | `faculty` | `Faculty@2026` | Assigned subject roster, assessment entry, class attendance, at-risk student watchlist, advisee management (`/faculty`) |
| **Student Dashboard** | `student` | `student` | `Student@2026` | Enrolled student profile, course assessments, class attendance records, class advisor details, and AI insights (`/student`) |

*Tip: The `/login` page includes convenient one-click demo autofill chips for all three accounts.*

---

## Running the Application

Start the Flask server:
```bash
python3 app.py
```

The application will run on:
- **Local URL**: `http://127.0.0.1:5002`

Open your web browser and navigate to:
- **Login Portal**: [http://127.0.0.1:5002/login](http://127.0.0.1:5002/login)
- **Coordinator Workspace**: [http://127.0.0.1:5002/](http://127.0.0.1:5002/) (Coordinator access)
- **Faculty Portal**: [http://127.0.0.1:5002/faculty](http://127.0.0.1:5002/faculty) (Faculty access)
- **Student Dashboard**: [http://127.0.0.1:5002/student](http://127.0.0.1:5002/student) (Student access with strict record isolation)

---

## Module-by-Module Documentation

### 1. Authentication & Role-Based Access Control (RBAC)
- **Routes**: `/login` (GET/POST), `/logout` (GET), `/api/auth/login` (POST), `/api/auth/logout` (POST), `/api/auth/me` (GET).
- **Security**: Passwords hashed with `scrypt` via Werkzeug (`generate_password_hash`). Plaintext passwords are never stored. User sessions track `user_id`, `username`, `role`, `student_id`, and `faculty_id`.
- **Role-Based Redirection & Access Control**:
  - **Coordinator**: Directed to Coordinator Workspace (`/`). Full system administration.
  - **Faculty**: Directed to Faculty Portal (`/faculty`). Teaching allocations, class rosters, marks, and attendance.
  - **Student**: Directed to Student Dashboard (`/student`). Strict student record isolation: students may only view their own profile, marks, attendance, and AI academic insights.

### 2. Coordinator Dashboard
- **Route**: `/` (`index.html`)
- **4 Key Statistic Cards**:
  1. Total Registered Students
  2. Total Active Curriculum Subjects
  3. High Risk Students requiring immediate follow-up
  4. Average Performance percentage across all recorded marks
- **Visual Analytics (Chart.js)**:
  - **Student Risk Distribution**: Interactive doughnut chart displaying counts of High, Medium, Low, and Insufficient Data with dynamic center student counter.
  - **Department-wise Student Distribution**: Bar chart displaying student density across college departments.
- **Navigation Tabs**: Students, Subjects, Marks, Attendance, Faculty, Faculty Assignments, Performance, Student Accounts, Class Advisors.

### 3. Student Management
- **Endpoints**: `POST /api/students`, `GET /api/students`, `PUT /api/students/<id>`, `DELETE /api/students/<id>`, `GET /api/students/<id>/dependencies`.
- **Features**:
  - Add student with validation (academic year 1-6, unique roll number).
  - Search by name or roll number.
  - Filter by Department and Academic Year.
  - Edit student details modal with live update.
  - Safe deletion dialog with dependency check. Under **Strict Academic Protection**, students with recorded marks, attendance records, or user accounts cannot be deleted until associated records are cleared.

### 4. Student Login Account Management *(New)*
- **Endpoints**:
  - `GET /api/students-without-accounts` — Students not yet assigned a login account.
  - `GET /api/student-accounts` — All student login accounts with status.
  - `POST /api/student-accounts` — Create a login account for an existing student.
  - `POST /api/student-accounts/<id>/reset-password` — Reset student password (coordinator only).
  - `PATCH /api/student-accounts/<id>/status` — Activate or deactivate an account.
  - `DELETE /api/student-accounts/<id>` — Remove student login account (preserves student record).
- **Features**:
  - Coordinator selects an existing student from a dropdown; read-only fields auto-fill.
  - Prevents duplicate usernames and multiple accounts per student.
  - Account status badge: Active / Deactivated / No Account.
  - Search by student name, roll number, or username.
  - Password stored with Werkzeug `scrypt` hash; plaintext never stored.
  - Both `users` insert and `students` link use a single database transaction.

### 5. Faculty Management & Teaching Allocations
- **Endpoints**: `POST /api/faculty`, `GET /api/faculty`, `PUT /api/faculty/<id>`, `DELETE /api/faculty/<id>`, `POST /api/faculty-assignments`, `GET /api/faculty-assignments`, `DELETE /api/faculty-assignments/<id>`.
- **Faculty Assignment Preview**: `GET /api/faculty-assignments/preview-students?faculty_id=&subject_id=&year=&section=` — Returns students matching the assignment criteria before submission.
- **Features**:
  - Register faculty members with department, email, and portal credentials.
  - Assign faculty members to specific subjects, academic years, and class sections.
  - Live student preview shows matching students before confirming the assignment.
  - Duplicate assignment prevention (`UNIQUE(faculty_id, subject_id, year, section)`).
  - Unassign course section or edit faculty details.

### 6. Class Advisor Assignment *(New)*
- **Endpoints**:
  - `GET /api/class-advisors` — All active class advisor assignments.
  - `POST /api/class-advisors` — Assign a faculty member as advisor for individual student.
  - `POST /api/class-advisors/bulk` — Bulk assign an advisor for all students in a section.
  - `POST /api/class-advisors/assign-student` — Assign or change advisor for a specific student.
  - `DELETE /api/class-advisors/<assignment_id>` — Remove a class advisor assignment.
  - `GET /api/class-advisors/preview?faculty_id=&year=&section=&department=` — Preview students before bulk assignment.
- **Assignment Rules**:
  - Each student has at most one **active** Class Advisor enforced by a partial unique index.
  - Re-assigning deactivates the previous assignment automatically.
  - Faculty can advise students across any department.
  - Maintains full assignment history (prior assignments kept with `is_active=0`).
- **Faculty Advisees Tab** (`/faculty` dashboard): Faculty can view all their assigned advisees with risk badge, attendance %, average score, and direct mentorship link.
- **Student Dashboard**: Shows assigned Class Advisor name, department, and email in a teal banner.

### 7. Subject Management
- **Endpoints**: `POST /api/subjects`, `GET /api/subjects`, `PUT /api/subjects/<id>`, `DELETE /api/subjects/<id>`, `GET /api/subjects/<id>/dependencies`.
- **Features**:
  - Register curriculum courses with unique subject codes.
  - Edit subject code and title via modal.
  - Delete subject with dependency verification. Deletion is blocked if marks, attendance, or faculty allocations exist for that course.

### 8. Marks Management
- **Endpoints**: `POST /api/marks`, `GET /api/marks`, `PUT /api/marks/<id>`, `DELETE /api/marks/<id>`.
- **Features**:
  - Select student and subject from dynamic dropdowns.
  - Enforce $0 \le \text{marks\_obtained} \le \text{max\_marks}$.
  - Edit existing assessment record via modal.
  - Delete record with immediate recalculation of student average and risk level across dashboard.

### 9. Attendance Management
- **Endpoints**: `POST /api/attendance`, `GET /api/attendance`, `GET /api/attendance/<id>`, `PUT /api/attendance/<id>`, `DELETE /api/attendance/<id>`.
- **Features**:
  - Record classes attended and total classes with upsert conflict resolution.
  - Validation: $0 \le \text{attended\_classes} \le \text{total\_classes}$.
  - Edit total and attended classes via dedicated modal.
  - Delete attendance record with instant dashboard refresh.

### 10. Student Performance Analysis
- **Endpoint**: `GET /api/performance`
- **Features**:
  - Comprehensive table listing roll number, student name, department, average marks, attendance %, and color-coded risk badge.
  - Search by student name or roll number.
  - Multi-criteria filter by Department and Risk Level (`High`, `Medium`, `Low`, `Insufficient Data`).
  - One-click link to Individual Student Analysis profile.

### 11. Faculty Portal
- **Routes**: `/faculty` (`faculty_dashboard.html`), `GET /api/faculty/<id>/dashboard`.
- **Features**:
  - Personalized greeting and teaching statistics (5 stat cards including Advisees count).
  - **My Subjects**: Courses and sections allocated to the faculty.
  - **My Students**: Class roster of students in assigned sections.
  - **My Advisees**: Students for whom this faculty is the designated Class Advisor, with risk badge, attendance %, and mentorship link.
  - **Marks**: Enter assessment scores for assigned classes and view marks history.
  - **Attendance**: Update class attendance for assigned courses.
  - **Performance**: Class overview of average scores and attendance with direct links to AI insights.
  - Faculty access is restricted to their authorized subjects and sections.

### 12. Individual Student Analysis & Staff AI Insights
- **Routes**: `/student-analysis?id=<student_id>`, `GET /api/students/<id>/analysis`, `POST /api/students/<id>/ai-insights`.
- **Features**:
  - Staff preview mode for Coordinators and Faculty members.
  - Profile header with roll number, department, year, and section.
  - 3 KPI metric cards: Average Marks, Attendance Percentage, Risk Classification.
  - Assessment records table and class attendance records.
  - **AI Performance Insights Card**: Analyzes student performance data and generates structured recommendations.

### 13. Student Portal & Dedicated Dashboard
- **Routes**: `/student` or `/student/dashboard` (`student_dashboard.html`), `GET /api/student/dashboard`, `POST /api/student/ai-insights`.
- **Features**:
  - Authenticated student portal displaying only the logged-in student's personal academic records.
  - Profile card with department, academic year, class section, roll number, and **assigned Class Advisor**.
  - **Class Advisor Banner**: Shows the advisor's name, department, and email when a Class Advisor is assigned.
  - Academic overview metrics: overall average percentage, attendance percentage, subject count, and risk classification tier.
  - Attendance shortage warnings alert with calculated classes needed to reach institutional 75% requirement.
  - Subject-by-subject assessment scores breakdown with individual assessment marks.
  - Direct local AI academic recommendations button using authenticated session context.
  - **Strict Record Isolation**: Session-enforced student ID guarantees that students cannot view or query other students' academic records.

---

## AI Integration & Fallback Engine

### Local AI Architecture
EduTrack Lite connects directly to a locally hosted **Ollama** service running `qwen3.5:4b`:
- **Endpoint**: `http://127.0.0.1:11434/api/chat`
- **Privacy**: Zero external cloud API calls; student grades and attendance remain 100% private and on-premise.
- **Data Fed to AI**: Student full name, department, overall average marks %, attendance %, existing risk classification, subject-wise assessment scores, and subject-wise attendance percentages.

### Report Output Structure
The AI produces an academic assessment formatted in four mandatory sections:
1. **Risk Classification Explanation**: Explains why the student is classified under their current risk level using recorded metrics.
2. **Visible Strengths**: Highlights specific recorded course scores $\ge 60\%$ or high attendance.
3. **Areas Needing Improvement**: Identifies measurable gaps (e.g. attendance below 75% or scores $< 50\%$).
4. **Practical and Supportive Recommendations**: Exactly three realistic, numbered, and actionable academic suggestions.

### Academic Heuristic Fallback Engine
To guarantee **100% uptime** during college presentations and grading even when Ollama is offline or not installed on the evaluator's machine:
- If Ollama is unreachable, times out, or returns an error, the backend automatically activates the built-in **Academic Heuristic Rule Engine**.
- The fallback engine computes student trends and formats the report with the exact same four headings and three numbered recommendations.
- The UI notifies the user gracefully: `[Ollama service unavailable. Insights generated via EduTrack Lite Academic Heuristic Engine.]`

---

## Test Suite & Verification Results

Two comprehensive verification test suites are included:

### test_auth_rbac.py — Authentication & RBAC (16 tests)
```
======================================================================
EDUTRACK LITE AUTH & RBAC TEST SUITE
======================================================================
[PASS] test_01: Coordinator login succeeds
[PASS] test_02: Faculty login succeeds
[PASS] test_03: Student login succeeds
[PASS] test_04: Invalid credentials rejected (401)
[PASS] test_05: Coordinator accesses coordinator dashboard
[PASS] test_06: Faculty redirected from coordinator dashboard
[PASS] test_07: Student blocked from coordinator dashboard
[PASS] test_08: Faculty accesses faculty dashboard
[PASS] test_09: Coordinator redirected from faculty dashboard
[PASS] test_10: Student blocked from faculty dashboard
[PASS] test_11: Student accesses student dashboard
[PASS] test_12: Faculty blocked from student dashboard
[PASS] test_13: Coordinator blocked from student dashboard
[PASS] test_14: Logout clears session
[PASS] test_15: Protected route inaccessible after logout
[PASS] test_16: Student record isolation enforced
======================================================================
STATUS: 16/16 PASSED — 100% SUCCESS RATE
======================================================================
```

### test_full_system.py — Full System Integration (49 tests)
```
======================================================================
EDUTRACK LITE FULL SYSTEM TEST SUITE
======================================================================
[PASS] Tests 01-08:  Student Account Management (create, list, reset password, toggle status, delete)
[PASS] Tests 09-15:  Faculty Assignment with Preview (preview API, assignment, duplicate block)
[PASS] Tests 16-25:  Class Advisor Assignment (bulk assign, individual assign, re-assign, deactivate, history)
[PASS] Tests 26-32:  Faculty Dashboard Advisees (advisee count, advisee list, search)
[PASS] Tests 33-38:  Student Dashboard Class Advisor (banner shown/hidden, advisor details)
[PASS] Tests 39-45:  Security & RBAC (student can't access admin routes, faculty boundary checks)
[PASS] Tests 46-49:  Data Preservation (all 6 students, 8 faculty, 30 marks, 29 attendance preserved)
======================================================================
STATUS: 49/49 PASSED — 100% SUCCESS RATE
======================================================================
```

**Total: 65/65 tests PASS across both suites.**

Run all tests:
```bash
cd /Users/aakash/Desktop/EduTrack-Lite
.venv/bin/python test_auth_rbac.py
.venv/bin/python test_full_system.py
```

---

## Project File Structure & Inventory

```
EduTrack-Lite/
├── app.py                      # Core Flask application, REST APIs, & AI controller
├── database.py                 # SQLite schema, foreign key enforcement, & default seeding
├── edutrack.db                 # SQLite database (existing records preserved)
├── edutrack_backup_*.db        # Safety backup created before schema migrations
├── requirements.txt            # Python dependencies
├── README.md                   # Complete project documentation
├── test_auth_rbac.py           # 16-test authentication & RBAC verification suite
├── test_full_system.py         # 49-test full system integration suite
├── static/
│   ├── style.css               # Complete responsive academic design system
│   ├── script.js               # Coordinator workspace, CRUD, modals, & Chart.js logic
│   └── student_analysis.js     # Student analysis profile & AI insight renderer
└── templates/
    ├── index.html              # Coordinator Dashboard & Workspace
    ├── faculty_dashboard.html  # Faculty Teaching Portal
    ├── student_dashboard.html  # Student Personal Dashboard & AI Insights
    ├── student_analysis.html   # Individual Student Analysis Profile (staff view)
    └── login.html              # Portal Authentication & Sign In
```

### Summary of All Modifications & Deliverables:
1. `app.py`: Authentication routes, Subject/Marks/Attendance/Faculty CRUD, Faculty Dashboard API, Student Account Management API, Class Advisor Assignment API, Faculty Assignment Preview API, AI Heuristic Fallback Engine. Full role-based access control on every protected endpoint.
2. `database.py`: Safe default seeding for coordinator, faculty, and student credentials. `class_advisor_assignments` table creation with partial unique index. `is_active` column on `users` table.
3. `templates/index.html`: Student Accounts tab (create, list, search, manage), Class Advisors tab (bulk section assignment, individual assignment, live preview, active advisors table), Faculty Assignment with Department field and live student preview container.
4. `templates/faculty_dashboard.html`: My Advisees tab, 5th stat card (Advisees count), advisee table with risk badge, mentorship links.
5. `templates/student_dashboard.html`: Class Advisor profile field, Advisor Banner (shown when advisor is assigned), `renderAll()` reads `class_advisor` from API.
6. `templates/login.html`: Modern portal login with one-click demo credential autofill chips for all three accounts.
7. `templates/student_analysis.html`: Polished topbar navigation, portal badge, and empty state rows.
8. `static/script.js`: Full Student Account Management JS, Faculty Assignment preview, Class Advisor Assignment JS (bulk + individual + preview), Faculty Advisees rendering.
9. `static/student_analysis.js`: Empty states and offline notice display.
10. `static/style.css`: Status badge classes (`.status-badge-active`, `.status-badge-inactive`, `.status-badge-none`), advisor banner, action button variants.
11. `test_auth_rbac.py`: 16-test RBAC and authentication verification suite.
12. `test_full_system.py`: 49-test full system integration suite covering all new modules.
13. `requirements.txt` & `README.md`: Updated dependencies and comprehensive project documentation.
