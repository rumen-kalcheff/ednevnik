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
- Views: grade_list/add/edit/delete, absence_list/add/edit/delete, material_list/upload/edit/delete, schedule, statistics, students_by_class (AJAX)
- Валидация: дати не могат да бъдат в бъдещето
- URL prefix: `/teacher/`

### Фаза 5 — Ученически модул ✅
- Views: grade_list, absence_list, schedule, material_list, statistics, class_info
- URL prefix: `/student/`
- Templates: `templates/students/` (6 шаблона)

### Фаза 6 — Родителски модул ✅
- App: `parents/`
- Views: grade_list, absence_list, schedule, material_list, statistics
- Поддръжка на множество деца — dropdown за избор
- URL prefix: `/parent/`

### Фаза 7 — Chart.js графики ✅
- Bar chart в успеваемост на ученик (ФИ9) — среден успех по предмети
- Bar chart в успеваемост на родител (ФИ17)
- Bar chart в учителски статистики (ФИ24)
- Bar chart в административни справки (ФИ35) — среден успех и отсъствия по класове

### Фаза 8 — Административни справки и финализиране ✅
- ФИ35: `/admin-panel/statistics/` — карти, графики, таблица по класове, справка за отсъствия
- Редактиране на учебни материали от учители (раздел 2.2.3)
- Всички 36 функционални изисквания изпълнени

## Тестови данни в системата
- admin / admin123 (роля: admin)
- ivan_petrov (роля: teacher)
- todor_ivanov (роля: student, клас: 10А)
- petar_kalchev (роля: parent, свързан с todor_ivanov)

## Важни файлове
- Изисквания: `/Users/rumenkalchev/Desktop/Diploma/docu_versions/documentation_diploma3.docx`
- Проект: `/Users/rumenkalchev/Desktop/Diploma/ednevnik/`
- Стартиране: `cd ~/Desktop/Diploma/ednevnik && source venv/bin/activate && python manage.py runserver`
