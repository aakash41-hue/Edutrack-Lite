
const studentForm = document.getElementById("studentForm");
const message = document.getElementById("message");
const studentList = document.getElementById("studentList");

// Load registered students
async function loadStudents() {
    try {
        const response = await fetch("/api/students");
        const students = await response.json();

        studentList.innerHTML = "";

        students.forEach(student => {
            const row = document.createElement("tr");

            [
                student.roll_number,
                student.full_name,
                student.department,
                student.year,
                student.section || "-"
            ].forEach(value => {
                const cell = document.createElement("td");
                cell.textContent = value;
                row.appendChild(cell);
            });

            studentList.appendChild(row);
        });

    } catch (error) {
        message.textContent = "Unable to load students.";
        console.error(error);
    }
}

// Add a student
studentForm.addEventListener("submit", async function(event) {
    event.preventDefault();

    const studentData = {
        roll_number: document.getElementById("roll_number").value,
        full_name: document.getElementById("full_name").value,
        department: document.getElementById("department").value,
        year: document.getElementById("year").value,
        section: document.getElementById("section").value
    };

    try {
        const response = await fetch("/api/students", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(studentData)
        });

        const result = await response.json();

        if (!response.ok) {
            message.textContent = result.error;
            return;
        }

        message.textContent = result.message;
        studentForm.reset();

        await loadStudents();

    } catch (error) {
        message.textContent = "Something went wrong.";
        console.error(error);
    }
});

// Load students when page opens
loadStudents();



const subjectForm = document.getElementById("subjectForm");
const subjectMessage = document.getElementById("subjectMessage");
const subjectList = document.getElementById("subjectList");

// Load registered subjects
async function loadSubjects() {
    try {
        const response = await fetch("/api/subjects");
        const subjects = await response.json();

        subjectList.innerHTML = "";

        subjects.forEach(subject => {
            const row = document.createElement("tr");

            [subject.subject_code, subject.subject_name].forEach(value => {
                const cell = document.createElement("td");
                cell.textContent = value;
                row.appendChild(cell);
            });

            subjectList.appendChild(row);
        });

    } catch (error) {
        subjectMessage.textContent = "Unable to load subjects.";
        console.error(error);
    }
}

// Add a subject
subjectForm.addEventListener("submit", async function(event) {
    event.preventDefault();

    const subjectData = {
        subject_code: document.getElementById("subject_code").value,
        subject_name: document.getElementById("subject_name").value
    };

    try {
        const response = await fetch("/api/subjects", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(subjectData)
        });

        const result = await response.json();

        if (!response.ok) {
            subjectMessage.textContent = result.error;
            return;
        }

        subjectMessage.textContent = result.message;
        subjectForm.reset();

        await loadSubjects();

    } catch (error) {
        subjectMessage.textContent = "Something went wrong.";
        console.error(error);
    }
});

// Load subjects when page opens
loadSubjects();



const marksForm = document.getElementById("marksForm");
const marksMessage = document.getElementById("marksMessage");
const marksList = document.getElementById("marksList");

const markStudent = document.getElementById("markStudent");
const markSubject = document.getElementById("markSubject");

// Load students and subjects into dropdowns
async function loadMarkOptions() {
    const [studentResponse, subjectResponse] = await Promise.all([
        fetch("/api/students"),
        fetch("/api/subjects")
    ]);

    const students = await studentResponse.json();
    const subjects = await subjectResponse.json();

    students.forEach(student => {
        const option = document.createElement("option");
        option.value = student.student_id;
        option.textContent = `${student.roll_number} - ${student.full_name}`;
        markStudent.appendChild(option);
    });

    subjects.forEach(subject => {
        const option = document.createElement("option");
        option.value = subject.subject_id;
        option.textContent = `${subject.subject_code} - ${subject.subject_name}`;
        markSubject.appendChild(option);
    });
}

// Load marks records
async function loadMarks() {
    const response = await fetch("/api/marks");
    const marks = await response.json();

    marksList.innerHTML = "";

    marks.forEach(mark => {
        const row = document.createElement("tr");

        [
            mark.roll_number,
            mark.full_name,
            mark.subject_code,
            mark.assessment_name,
            mark.marks_obtained,
            mark.max_marks
        ].forEach(value => {
            const cell = document.createElement("td");
            cell.textContent = value;
            row.appendChild(cell);
        });

        marksList.appendChild(row);
    });
}

// Save marks
marksForm.addEventListener("submit", async function(event) {
    event.preventDefault();

    const data = {
        student_id: markStudent.value,
        subject_id: markSubject.value,
        assessment_name: document.getElementById("assessmentName").value,
        marks_obtained: document.getElementById("marksObtained").value,
        max_marks: document.getElementById("maxMarks").value
    };

    try {
        const response = await fetch("/api/marks", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (!response.ok) {
            marksMessage.textContent = result.error;
            return;
        }

        marksMessage.textContent = result.message;
        marksForm.reset();

        await loadMarks();

    } catch (error) {
        marksMessage.textContent = "Unable to save marks.";
        console.error(error);
    }
});

// Initialize marks section
loadMarkOptions();
loadMarks();



const attendanceForm = document.getElementById("attendanceForm");
const attendanceMessage = document.getElementById("attendanceMessage");
const attendanceList = document.getElementById("attendanceList");

const attendanceStudent = document.getElementById("attendanceStudent");
const attendanceSubject = document.getElementById("attendanceSubject");

// Load dropdown options
async function loadAttendanceOptions() {

    const [studentResponse, subjectResponse] = await Promise.all([
        fetch("/api/students"),
        fetch("/api/subjects")
    ]);

    const students = await studentResponse.json();
    const subjects = await subjectResponse.json();

    students.forEach(student => {
        const option = document.createElement("option");
        option.value = student.student_id;
        option.textContent = `${student.roll_number} - ${student.full_name}`;
        attendanceStudent.appendChild(option);
    });

    subjects.forEach(subject => {
        const option = document.createElement("option");
        option.value = subject.subject_id;
        option.textContent = `${subject.subject_code} - ${subject.subject_name}`;
        attendanceSubject.appendChild(option);
    });
}

// Load attendance records
async function loadAttendance() {

    const response = await fetch("/api/attendance");
    const records = await response.json();

    attendanceList.innerHTML = "";

    records.forEach(record => {

        const row = document.createElement("tr");

        [
            record.roll_number,
            record.full_name,
            record.subject_code,
            record.total_classes,
            record.attended_classes,
            `${record.attendance_percentage}%`
        ].forEach(value => {

            const cell = document.createElement("td");
            cell.textContent = value;
            row.appendChild(cell);

        });

        attendanceList.appendChild(row);

    });
}

// Save attendance
attendanceForm.addEventListener("submit", async function(event) {

    event.preventDefault();

    const data = {
        student_id: attendanceStudent.value,
        subject_id: attendanceSubject.value,
        total_classes: document.getElementById("totalClasses").value,
        attended_classes: document.getElementById("attendedClasses").value
    };

    try {

        const response = await fetch("/api/attendance", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (!response.ok) {
            attendanceMessage.textContent = result.error;
            return;
        }

        attendanceMessage.textContent = result.message;

        attendanceForm.reset();

        await loadAttendance();

    } catch (error) {

        attendanceMessage.textContent = "Unable to save attendance.";
        console.error(error);

    }

});

// Initialize attendance
loadAttendanceOptions();
loadAttendance();



const performanceList = document.getElementById("performanceList");

async function loadPerformance() {

    try {
        const response = await fetch("/api/performance");

        if (!response.ok) {
            throw new Error("Unable to fetch performance data");
        }

        const students = await response.json();

        performanceList.innerHTML = "";

        students.forEach(student => {

            const row = document.createElement("tr");

            const values = [
                student.roll_number,
                student.student_name,
                student.average_marks === null
                    ? "Not available"
                    : `${student.average_marks}%`,
                student.attendance_percentage === null
                    ? "Not available"
                    : `${student.attendance_percentage}%`,
                student.risk_level
            ];

            values.forEach((value, index) => {

                const cell = document.createElement("td");
                cell.textContent = value;

                if (index === 4) {
                    cell.classList.add(
                        "risk-" + student.risk_level
                            .toLowerCase()
                            .replaceAll(" ", "-")
                    );
                }

                row.appendChild(cell);

            });

            performanceList.appendChild(row);

        });

    } catch (error) {
        console.error(error);
    }
}

loadPerformance();
