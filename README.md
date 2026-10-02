# EduNova – School E-Gradebook & Timetable System

EduNova is a web-based electronic gradebook for Bulgarian secondary schools. Administrators, teachers, students and parents each get their own view of grades, absences, the weekly timetable and learning materials.

**Tech stack:** Python · Django · PostgreSQL · Bootstrap 5 · Chart.js
<br>The user interface is in Bulgarian.

## Highlights

- **Four roles** (administrator, teacher, student, parent), each with its own dashboard. A custom decorator checks the user's role on every view.
- **Timetable engine.** Timetables are edited as drafts and then published. Before publishing, the system checks for teacher, room and class clashes, curriculum hour limits, room types and foreign-language groups.
- **Substitutions.** When a teacher is absent, the system lists the affected lessons and suggests teachers who are free at that time. Students and parents get an email about each change.
- **Gradebook.** Teachers enter current, term and annual grades, either one at a time or for a whole class. Absences are linked to the real timetable, and parents get an email for each one.
- **Statistics, learning materials and lesson topics**, with Chart.js charts for every role.
- **Security basics:** password reset by email, sessions that expire after inactivity and secrets kept in environment variables.

## Structure

9 Django apps: `accounts`, `school`, `students`, `teachers`, `parents`, `grades`, `materials`, `timetable`, `adminpanel`.
The timetable business logic lives in [`timetable/services.py`](timetable/services.py).

## License

© 2026 Rumen Kalchev. All rights reserved.
This repository is published as a portfolio piece. You may not copy, reuse or redistribute the code without written permission.

**Contact:** rumenkalchev7@gmail.com · [LinkedIn](https://www.linkedin.com/in/rumen-kalchev-52b8391b7/)
