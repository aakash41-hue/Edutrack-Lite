
const studentId = new URLSearchParams(window.location.search).get("id");

async function loadStudentAnalysis() {

    if (!studentId || !/^\d+$/.test(studentId)) {
        document.getElementById("studentName").textContent =
            "Invalid student ID";
        return;
    }

    try {
        const response = await fetch(
            `/api/students/${studentId}/analysis`
        );

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || "Unable to load analysis");
        }

        const student = data.student;

        document.getElementById("studentName").textContent =
            student.full_name;

        document.getElementById("studentDetails").textContent =
            `Roll Number: ${student.roll_number} | Department: ${student.department} | Year: ${student.year} | Section: ${student.section || "-"}`;

        document.getElementById("averageMarks").textContent =
            data.average_marks === null
                ? "Not available"
                : `${data.average_marks}%`;

        document.getElementById("attendancePercentage").textContent =
            data.attendance_percentage === null
                ? "Not available"
                : `${data.attendance_percentage}%`;

        const risk = document.getElementById("riskLevel");

        risk.textContent = data.risk_level;
        risk.className = "risk-" + data.risk_level
            .toLowerCase()
            .replaceAll(" ", "-");

        // Display assessment records
        const marksBody = document.getElementById("analysisMarks");

        marksBody.replaceChildren();

        if (data.marks.length === 0) {
            const tr = document.createElement("tr");
            tr.className = "empty-row";
            tr.innerHTML = '<td colspan="4" class="empty-state-cell">No assessment marks recorded for this student.</td>';
            marksBody.appendChild(tr);
        } else {
            data.marks.forEach(mark => {
                const row = document.createElement("tr");
                [
                    `${mark.subject_code} - ${mark.subject_name}`,
                    mark.assessment_name,
                    `${mark.marks_obtained}/${mark.max_marks}`,
                    `${mark.percentage}%`
                ].forEach(value => {
                    const cell = document.createElement("td");
                    cell.textContent = value;
                    row.appendChild(cell);
                });
                marksBody.appendChild(row);
            });
        }

        // Display attendance records
        const attendanceBody =
            document.getElementById("analysisAttendance");

        attendanceBody.replaceChildren();

        if (data.attendance.length === 0) {
            const tr = document.createElement("tr");
            tr.className = "empty-row";
            tr.innerHTML = '<td colspan="4" class="empty-state-cell">No attendance records found for this student.</td>';
            attendanceBody.appendChild(tr);
        } else {
            data.attendance.forEach(record => {
                const row = document.createElement("tr");
                [
                    `${record.subject_code} - ${record.subject_name}`,
                    record.total_classes,
                    record.attended_classes,
                    `${record.percentage}%`
                ].forEach(value => {
                    const cell = document.createElement("td");
                    cell.textContent = value;
                    row.appendChild(cell);
                });
                attendanceBody.appendChild(row);
            });
        }

    } catch (error) {

        document.getElementById("studentName").textContent =
            error.message;

        console.error(error);

    }
}



function renderAIInsights(markdown, container) {

    container.replaceChildren();

    const lines = markdown.split("\n");
    let currentSection = null;
    let currentList = null;
    let currentListType = null;

    function addFormattedText(element, text) {
        const parts = text.split(/(\*\*.*?\*\*)/g);

        parts.forEach(part => {
            if (part.startsWith("**") && part.endsWith("**")) {
                const strong = document.createElement("strong");
                strong.textContent = part.slice(2, -2);
                element.appendChild(strong);
            } else {
                element.appendChild(document.createTextNode(part));
            }
        });
    }

    function startSection(title) {
        currentSection = document.createElement("section");
        currentSection.className = "ai-insight-section";

        const heading = document.createElement("h3");
        heading.textContent = title;

        currentSection.appendChild(heading);
        container.appendChild(currentSection);

        currentList = null;
        currentListType = null;
    }

    lines.forEach(line => {

        const trimmed = line.trim();

        if (!trimmed) {
            currentList = null;
            currentListType = null;
            return;
        }

        // Markdown headings
        if (/^#{1,4}\s+/.test(trimmed)) {
            const title = trimmed.replace(/^#{1,4}\s+/, "");
            startSection(title);
            return;
        }

        // Recognize numbered report section headings
        const sectionHeading = trimmed.match(
            /^\d+\.\s+(Analysis of Risk Classification|Reason for Risk Classification|Visible Strengths|Areas Needing Improvement|Practical and Supportive Recommendations|Practical Recommendations)$/i
        );

        if (sectionHeading) {
            startSection(sectionHeading[1]);
            return;
        }

        // Create an introductory section if the AI starts with a paragraph
        if (!currentSection) {
            currentSection = document.createElement("section");
            currentSection.className = "ai-insight-intro";
            container.appendChild(currentSection);
        }

        // Bullet and numbered lists
        const isBullet = /^[-*]\s+/.test(trimmed);
        const isNumbered = /^\d+\.\s+/.test(trimmed);

        if (isBullet || isNumbered) {

            const listType = isNumbered ? "ol" : "ul";

            if (!currentList || currentListType !== listType) {
                currentList = document.createElement(listType);
                currentListType = listType;
                currentSection.appendChild(currentList);
            }

            const item = document.createElement("li");

            const text = trimmed.replace(
                /^([-*]|\d+\.)\s+/,
                ""
            );

            addFormattedText(item, text);
            currentList.appendChild(item);
            return;
        }

        // Normal paragraphs
        currentList = null;
        currentListType = null;

        const paragraph = document.createElement("p");
        addFormattedText(paragraph, trimmed);
        currentSection.appendChild(paragraph);

    });
}


// Generate AI performance insights
async function generateAIInsights() {

    const button = document.getElementById("generateInsightsBtn");
    const status = document.getElementById("aiStatus");
    const content = document.getElementById("aiInsightsContent");

    if (!studentId || !/^\d+$/.test(studentId)) {
        status.textContent = "Invalid student ID.";
        return;
    }

    button.disabled = true;
    button.textContent = "Generating...";
    status.textContent = "AI is analyzing student performance. Please wait...";
    content.hidden = true;
    content.textContent = "";

    try {

        const response = await fetch(
            `/api/students/${studentId}/ai-insights`,
            {
                method: "POST"
            }
        );

        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                data.error || "Unable to generate AI insights."
            );
        }

        // Display the AI-generated explanation safely as text
        renderAIInsights(data.insights, content);
        content.hidden = false;

        let statusText = `AI analysis completed for ${data.student_name}. Risk classification: ${data.risk_level}.`;
        if (data.notice) {
            statusText += ` [${data.notice}]`;
        }
        status.textContent = statusText;

    } catch (error) {

        status.textContent = error.message;
        content.hidden = true;

        console.error("AI Insights Error:", error);

    } finally {

        button.disabled = false;
        button.textContent = "Generate AI Insights";

    }
}


// Button event
document.getElementById("generateInsightsBtn")
    .addEventListener("click", generateAIInsights);


// Load student information
loadStudentAnalysis();
