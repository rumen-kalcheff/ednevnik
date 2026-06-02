# Прогрес на разработката

## Завършени фази

### Фаза 1 — Инфраструктура ✅
- PostgreSQL 17 инсталиран и стартиран
- База данни: `ednevnik`
- Python venv: `venv/`
- Пакети: django 6.0.5, psycopg2-binary, pillow, python-decouple
- Django проект: `config/`
- `.env` файл с SECRET_KEY, DB настройки
- `settings.py` конфигуриран (PostgreSQL, bg locale, Europe/Sofia, session timeout 2ч)

### Фаза 2 — Автентикация и роли ✅
- Custom User модел с роли: admin, teacher, student, parent
- Login/Logout views
- `@role_required('роля')` декоратор
- 4 dashboard-а (по един за роля)
- Тестов потребител: admin / admin123

### Фаза 3 — Администраторски модул ✅
- Apps: `school`, `students`, `teachers`, `adminpanel`
- Модели: Subject, Class, TeacherClassSubject, StudentProfile, ParentProfile, TeacherProfile
- CRUD: потребители, класове, предмети, назначения (учител→клас+предмет), родител↔ученик
- При създаване на ученик се избира клас (dynamic dropdown)

### Фаза 4 — Учителски модул ✅
- Apps: `grades`, `materials`
- Модели: Grade (оценки 2-6, видове: устно/контролно/текуща), Absence (извинено/неизвинено), Material (файлове), Timetable
- Views в `teachers/views.py`: grade_list/add/edit/delete, absence_list/add/edit/delete, material_list/upload/delete, schedule, statistics, students_by_class (AJAX)
- Валидация: дати не могат да бъдат в бъдещето
- URL prefix: `/teacher/`

## Тестови данни в системата
- admin / admin123 (роля: admin)
- ivan_petrov (роля: teacher, преподава Математика в 10А)
- todor_ivanov (роля: student, клас: 10А)
- petar_kalchev (роля: parent, свързан с todor_ivanov)
- Клас: 10А, Предмет: Математика
- Назначение: ivan_petrov → 10А → Математика

### Фаза 5 — Ученически модул ✅
- Views: grade_list, absence_list, schedule, material_list, statistics
- URL prefix: `/student/`
- Templates: `templates/students/` (5 шаблона)
- Dashboard бутони свързани с реални URL-и
- Ученикът вижда само своите данни (филтриране по StudentProfile)

### ФИ11 — Моят клас (ученик) ✅
- View: class_info в students/views.py
- Показва: клас, класен ръководител, списък съученици
- URL: /student/class/

### Фаза 6 — Родителски модул ✅
- Нов app: `parents/` (views + urls, без модели)
- Views: grade_list, absence_list, schedule, statistics (без материали — не е в ФИ)
- Поддръжка на множество деца — dropdown бутони за избор
- URL prefix: `/parent/`
- Templates: `templates/parents/` (4 шаблона)
- Dashboard бутони свързани с реални URL-и

### Фаза 7 — Chart.js графики ✅
- Bar chart в Успеваемост на ученика (ФИ9) — среден успех по предмети
- Bar chart в Успеваемост на родителя (ФИ17) — същото за детето
- Цветове: зелено ≥5, жълто ≥4, оранжево ≥3, червено <3
- Chart.js 4.4.3 от CDN

### Допълнителни ФИ ✅
- ФИ1/ФИ2: Landing page за нерегистрирани (home.html) — показва функционалностите по роля
- ФИ18: Родителят вижда учебни материали (върнато, беше погрешно махнато)
- ФИ24: Chart.js графика в учителските статистики

## Следващи фази
- **Фаза 8** — Тестване и финализиране (ФИ35: административни справки)

## Важни файлове
- Изисквания: `/Users/rumenkalchev/Desktop/Diploma/docu_versions/documentation_diploma3.docx`
- Проект: `/Users/rumenkalchev/Desktop/Diploma/ednevnik/`
- Стартиране: `cd ~/Desktop/Diploma/ednevnik && source venv/bin/activate && python manage.py runserver`
