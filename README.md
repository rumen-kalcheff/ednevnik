# EduNova – School E-Gradebook & Timetable System

eDnevnik is a web-based electronic gradebook for Bulgarian secondary schools. Administrators, teachers, students and parents each get their own view of grades, absences, the weekly timetable and learning materials. I built it as my diploma thesis at the Technical University of Sofia (Computer and Software Engineering, 2026).

> The user interface is in Bulgarian.

**Tech stack:** Python 3 · Django 6 · PostgreSQL · Bootstrap 5 · Chart.js

---

## Features

### Roles and access
- Four roles with separate dashboards: **administrator**, **teacher**, **student** and **parent**.
- Each view checks the user's role through a custom `@role_required` decorator.
- Password change and password reset by email. The reset link is valid for 24 hours.
- Sessions expire after 2 hours of inactivity.

### Administrator
- Manage users, classes, subjects and teacher–class–subject assignments.
- Link parents to their children.
- View school-wide statistics.
- **Timetable management:**
  - Configure rooms, shifts, periods and the weekly curriculum (hours per subject).
  - Edit each class's timetable as a **draft** and **publish** it once it is ready.
  - Before publishing, the system checks that no teacher, room or class is double-booked, that curriculum hour limits are respected, that rooms suit the subject (gym, computer lab) and that foreign-language groups are consistent.
- **Teacher absences and substitutions:** when a teacher is marked absent, the system lists the affected lessons and suggests teachers who are free at that time. The admin can assign a substitute or cancel the lesson, and students and parents get an email about the change.

### Teacher
- Enter grades one at a time or for a whole class at once: current, oral and written grades, plus term and annual grades.
- Record absences against the lessons the teacher actually has in the published timetable. Parents get an email for each absence.
- Log lesson topics and upload learning materials.
- See their personal weekly schedule, substitutions and class statistics.
- Homeroom teachers get an overview of their class.

### Student and parent
- Grades grouped by subject, with a filter by term.
- Absences, the weekly schedule, learning materials and teacher contacts.
- Statistics with Chart.js charts.
- A parent with more than one child in the school can switch between them.

---

## Project structure

| App          | Responsibility                                                      |
|--------------|---------------------------------------------------------------------|
| `accounts`   | Custom `User` model with roles, login, password flows, role decorators |
| `school`     | Classes, subjects, teacher–class–subject assignments                |
| `students`   | Student and parent profiles, student views                          |
| `teachers`   | Teacher profiles and teacher views (grades, absences, materials)    |
| `parents`    | Parent views                                                        |
| `grades`     | Grades and absences                                                 |
| `materials`  | Uploaded learning materials                                         |
| `timetable`  | School years, shifts, periods, rooms, curriculum, timetable versions, lessons, substitutions |
| `adminpanel` | Administrator panel and statistics                                  |

The timetable business logic (validation, publishing, choosing substitutes) is in [`timetable/services.py`](timetable/services.py). The views only call it.

---

## Getting started

### Prerequisites
- Python 3.12+
- PostgreSQL

### 1. Clone and install

```bash
git clone https://github.com/rumen-kalcheff/ednevnik.git
cd ednevnik
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Create the database

```bash
createdb ednevnik
```

### 3. Configure environment variables

Create a `.env` file in the project root:

```env
SECRET_KEY=change-me
DEBUG=True

DB_NAME=ednevnik
DB_USER=postgres
DB_PASSWORD=
DB_HOST=localhost
DB_PORT=5432

# Print emails to the console instead of sending them
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
# To send real emails over SMTP (e.g. Gmail with an app password), remove the line above and set:
# EMAIL_HOST_USER=you@gmail.com
# EMAIL_HOST_PASSWORD=your-app-password
```

### 4. Migrate and create an administrator

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py shell -c "from accounts.models import User; User.objects.filter(is_superuser=True).update(role='admin')"
```

### 5. (Optional) Sample timetable data

When you already have classes, subjects and teacher assignments, this command fills in rooms, shifts, the curriculum and a timetable:

```bash
python manage.py seed_timetable          # add --reset to rebuild this year's timetables
```

### 6. Run

```bash
python manage.py runserver
```

Open http://127.0.0.1:8000 and log in with the administrator account.

---

## Author

**Rumen Kalchev** · [GitHub](https://github.com/rumen-kalcheff) · [LinkedIn](https://www.linkedin.com/in/rumen-kalchev-52b8391b7/)
