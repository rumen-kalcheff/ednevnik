"""Проверки и помощни функции за учебното разписание.

Всички проверки живеят тук, за да се изпълняват на сървъра при всяко
записване — независимо какво е показал или скрил интерфейсът.
"""

from collections import Counter
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from accounts.models import User
from school.models import TeacherClassSubject
from .models import (
    ClassYearSetting, CurriculumEntry, Lesson, Substitution,
    TeacherAbsence, TimetableVersion,
)


DAYS = [1, 2, 3, 4, 5]
DAY_NAMES = dict(Lesson.DAY_CHOICES)

# Отсъствие, което още не е отказано, прави преподавателя неподходящ за заместник.
BLOCKING_ABSENCE_STATUSES = (TeacherAbsence.PENDING, TeacherAbsence.APPROVED)

# Предпазна граница при обхождане на дните на едно отсъствие.
MAX_ABSENCE_DAYS = 120


# ── Настройки и версии ────────────────────────────────────────

def class_setting(school_year, school_class):
    """Смяна и чужди езици на клас за учебната година (или None)."""
    return ClassYearSetting.objects.filter(
        school_year=school_year, school_class=school_class
    ).select_related('shift', 'first_language', 'second_language').first()


def class_periods(school_year, school_class):
    """Учебните периоди на смяната, в която учи класът."""
    setting = class_setting(school_year, school_class)
    if not setting:
        return []
    return list(setting.shift.periods.all())


def published_version(school_year, school_class):
    return TimetableVersion.objects.filter(
        school_year=school_year, school_class=school_class,
        status=TimetableVersion.PUBLISHED,
    ).first()


def draft_version(school_year, school_class):
    return TimetableVersion.objects.filter(
        school_year=school_year, school_class=school_class,
        status=TimetableVersion.DRAFT,
    ).first()


def working_version(school_year, school_class):
    """Версията, с която работи администраторът: черновата, ако има такава,
    иначе публикуваната."""
    return (draft_version(school_year, school_class)
            or published_version(school_year, school_class))


def working_versions(school_year, exclude_class=None):
    """За всеки клас — по една версия: черновата, ако има, иначе публикуваната.
    Спрямо тях се проверяват конфликтите на преподавател и зала."""
    versions = TimetableVersion.objects.filter(
        school_year=school_year,
        status__in=[TimetableVersion.DRAFT, TimetableVersion.PUBLISHED],
    ).select_related('school_class')

    if exclude_class is not None:
        versions = versions.exclude(school_class=exclude_class)

    chosen = {}
    for version in versions:
        if version.school_class_id not in chosen or version.is_draft:
            chosen[version.school_class_id] = version
    return list(chosen.values())


@transaction.atomic
def get_or_create_draft(school_year, school_class, user):
    """Черновата на класа. При редакция на публикувано разписание се създава
    нова чернова — копие на публикуваното, така че учителите, учениците и
    родителите продължават да виждат старата версия."""
    draft = draft_version(school_year, school_class)
    if draft:
        return draft

    draft = TimetableVersion.objects.create(
        school_year=school_year, school_class=school_class,
        status=TimetableVersion.DRAFT, created_by=user,
    )
    published = published_version(school_year, school_class)
    if published:
        Lesson.objects.bulk_create([
            Lesson(
                version=draft, day_of_week=lesson.day_of_week,
                period=lesson.period, subject=lesson.subject,
                teacher=lesson.teacher, room=lesson.room,
            )
            for lesson in published.lessons.all()
        ])
    return draft


# ── Проверки за конфликт при записване на час ─────────────────

def check_lesson(version, day_of_week, period, subject, teacher, room, exclude_lesson=None):
    """Връща списък със съобщения за причините часът да не може да се запише.
    Празен списък означава, че часът е допустим."""
    errors = []
    school_class = version.school_class

    # Конфликт със смяната — часът трябва да е в смяната на класа.
    setting = class_setting(version.school_year, school_class)
    if setting is None:
        errors.append(f'Класът {school_class} няма зададена смяна за {version.school_year}.')
    elif period.shift_id != setting.shift_id:
        errors.append(
            f'{period.number}. час ({period.start_time:%H:%M}) е извън '
            f'{setting.shift} — смяната на клас {school_class}.'
        )

    # Конфликт на клас — един клас има най-много един час в даден ден и период.
    class_clash = Lesson.objects.filter(
        version=version, day_of_week=day_of_week, period=period,
    )
    if exclude_lesson is not None:
        class_clash = class_clash.exclude(pk=exclude_lesson.pk)
    clash = class_clash.select_related('subject').first()
    if clash:
        errors.append(
            f'Клас {school_class} вече има час по {clash.subject} в '
            f'{DAY_NAMES.get(day_of_week, day_of_week).lower()}, {period.number}. час.'
        )

    # Преподавателят трябва да има право да преподава предмета на този клас.
    if not TeacherClassSubject.objects.filter(
        teacher=teacher, school_class=school_class, subject=subject
    ).exists():
        errors.append(
            f'{teacher.get_full_name()} не е назначен(а) да преподава '
            f'{subject} на клас {school_class}.'
        )

    # Подходящ тип зала за предмета.
    if subject.required_room_type and room.room_type != subject.required_room_type:
        errors.append(
            f'{subject} изисква {subject.get_required_room_type_display().lower()}, '
            f'а зала {room} е {room.get_room_type_display().lower()}.'
        )

    if not room.is_active:
        errors.append(f'Зала {room} е деактивирана.')

    # Конфликт на преподавател и на зала — спрямо разписанията на другите класове.
    others = Lesson.objects.filter(
        version__in=working_versions(version.school_year, exclude_class=school_class),
        day_of_week=day_of_week, period=period,
    ).select_related('version__school_class', 'teacher', 'room')

    day_label = DAY_NAMES.get(day_of_week, day_of_week).lower()
    for other in others:
        if other.teacher_id == teacher.pk:
            errors.append(
                f'{teacher.get_full_name()} вече води час на клас '
                f'{other.version.school_class} в {day_label}, {period.number}. час.'
            )
        if other.room_id == room.pk:
            errors.append(
                f'Зала {room} е заета от клас {other.version.school_class} в '
                f'{day_label}, {period.number}. час.'
            )

    return errors


def check_curriculum_capacity(version, subject, exclude_lesson=None):
    """Часът не трябва да надхвърля седмичния хорариум на класа."""
    entry = CurriculumEntry.objects.filter(
        school_year=version.school_year, school_class=version.school_class,
        subject=subject,
    ).first()
    if entry is None:
        return [f'{subject} не е в седмичния хорариум на клас {version.school_class}.']

    placed = Lesson.objects.filter(version=version, subject=subject)
    if exclude_lesson is not None:
        placed = placed.exclude(pk=exclude_lesson.pk)
    if placed.count() >= entry.hours_per_week:
        return [
            f'Хорариумът по {subject} за клас {version.school_class} е '
            f'{entry.hours_per_week} ч. седмично и вече е запълнен.'
        ]
    return []


# ── Проверки при публикуване ──────────────────────────────────

def validate_for_publish(version):
    """Разписанието се публикува само ако съвпада с хорариума и няма конфликти."""
    errors = []
    school_class = version.school_class
    setting = class_setting(version.school_year, school_class)

    if setting is None:
        errors.append(f'Клас {school_class} няма зададена смяна за {version.school_year}.')

    curriculum = list(CurriculumEntry.objects.filter(
        school_year=version.school_year, school_class=school_class,
    ).select_related('subject'))
    if not curriculum:
        errors.append(f'Не е зададен седмичен хорариум за клас {school_class}.')

    lessons = list(version.lessons.select_related('subject', 'period', 'teacher', 'room'))
    if not lessons:
        errors.append('Разписанието е празно.')

    placed = Counter(lesson.subject_id for lesson in lessons)

    # Точно толкова часове, колкото са зададени в хорариума.
    for entry in curriculum:
        count = placed.get(entry.subject_id, 0)
        if count < entry.hours_per_week:
            errors.append(
                f'{entry.subject}: поставени са {count} от {entry.hours_per_week} часа — '
                f'липсват {entry.hours_per_week - count}.'
            )
        elif count > entry.hours_per_week:
            errors.append(
                f'{entry.subject}: поставени са {count} часа при хорариум '
                f'{entry.hours_per_week} — {count - entry.hours_per_week} в повече.'
            )

    # Часове по предмет извън хорариума.
    curriculum_ids = {entry.subject_id for entry in curriculum}
    for subject_id in placed:
        if subject_id not in curriculum_ids:
            subject = next(l.subject for l in lessons if l.subject_id == subject_id)
            errors.append(f'{subject} не е в седмичния хорариум на клас {school_class}.')

    errors.extend(_language_errors(setting, curriculum))

    # Всеки поставен час трябва да е без конфликт и в момента на публикуване.
    for lesson in lessons:
        errors.extend(check_lesson(
            version, lesson.day_of_week, lesson.period, lesson.subject,
            lesson.teacher, lesson.room, exclude_lesson=lesson,
        ))

    # Един и същ текст може да дойде от няколко часа — показваме го веднъж.
    unique_errors = []
    for error in errors:
        if error not in unique_errors:
            unique_errors.append(error)
    return unique_errors


def _language_errors(setting, curriculum):
    """Точно два чужди езика, като първият е с по-голям хорариум от втория."""
    if setting is None:
        return []

    errors = []
    hours = {entry.subject_id: entry.hours_per_week for entry in curriculum}
    languages = [entry for entry in curriculum
                 if entry.subject.is_foreign_language and entry.hours_per_week > 0]

    if not setting.first_language or not setting.second_language:
        errors.append(f'Не са зададени двата чужди езика на клас {setting.school_class}.')
    else:
        if setting.first_language_id == setting.second_language_id:
            errors.append('Първият и вторият чужд език не могат да съвпадат.')
        first_hours = hours.get(setting.first_language_id, 0)
        second_hours = hours.get(setting.second_language_id, 0)
        if not first_hours:
            errors.append(f'{setting.first_language} (първи чужд език) няма зададен хорариум.')
        if not second_hours:
            errors.append(f'{setting.second_language} (втори чужд език) няма зададен хорариум.')
        if first_hours and second_hours and first_hours <= second_hours:
            errors.append(
                f'Първият чужд език ({setting.first_language} — {first_hours} ч.) трябва да е '
                f'с повече часове от втория ({setting.second_language} — {second_hours} ч.).'
            )

    if len(languages) != 2:
        names = ', '.join(entry.subject.name for entry in languages) or 'няма'
        errors.append(
            f'Клас {setting.school_class} трябва да изучава точно два чужди езика, '
            f'а в хорариума са {len(languages)} ({names}).'
        )
    elif setting.first_language and setting.second_language:
        chosen = {setting.first_language_id, setting.second_language_id}
        for entry in languages:
            if entry.subject_id not in chosen:
                errors.append(
                    f'{entry.subject} е в хорариума, но не е избран като първи или '
                    f'втори чужд език на клас {setting.school_class}.'
                )
    return errors


@transaction.atomic
def publish(version, user):
    """Публикува версията. Връща списък с грешки — празен при успех."""
    errors = validate_for_publish(version)
    if errors:
        return errors

    TimetableVersion.objects.filter(
        school_year=version.school_year, school_class=version.school_class,
        status=TimetableVersion.PUBLISHED,
    ).exclude(pk=version.pk).update(status=TimetableVersion.ARCHIVED)

    version.status = TimetableVersion.PUBLISHED
    version.published_at = timezone.now()
    version.published_by = user
    version.save(update_fields=['status', 'published_at', 'published_by'])
    return []


# ── Седмични решетки ──────────────────────────────────────────

def week_grid(version, periods):
    """Решетка {период: {ден: час}} за седмичното разписание на един клас."""
    lessons = {}
    if version is not None:
        for lesson in version.lessons.select_related('subject', 'teacher', 'room', 'period'):
            lessons[(lesson.period_id, lesson.day_of_week)] = lesson
    return [
        {'period': period,
         'cells': [{'day': day, 'lesson': lessons.get((period.pk, day))} for day in DAYS]}
        for period in periods
    ]


def teacher_week_grid(school_year, teacher):
    """Седмичното разписание на преподавател — от публикуваните разписания
    на всички класове, подредено по начален час."""
    lessons = Lesson.objects.filter(
        version__school_year=school_year,
        version__status=TimetableVersion.PUBLISHED,
        teacher=teacher,
    ).select_related('subject', 'room', 'period', 'period__shift', 'version__school_class')

    periods = sorted({lesson.period for lesson in lessons},
                     key=lambda p: (p.start_time, p.number))
    by_slot = {(lesson.period_id, lesson.day_of_week): lesson for lesson in lessons}
    return [
        {'period': period,
         'cells': [{'day': day, 'lesson': by_slot.get((period.pk, day))} for day in DAYS]}
        for period in periods
    ]


# ── Часове за конкретна дата ──────────────────────────────────

def lessons_on_date(school_year, day_date, teacher=None, school_class=None):
    """Часовете за конкретна календарна дата заедно със заместванията.

    Връща списък от речници с ключове: lesson, substitution, teacher
    (действителният преподавател за деня), is_cancelled.
    """
    day_of_week = day_date.isoweekday()
    if day_of_week not in DAYS:
        return []

    lessons = Lesson.objects.filter(
        version__school_year=school_year,
        version__status=TimetableVersion.PUBLISHED,
        day_of_week=day_of_week,
    ).select_related('subject', 'teacher', 'room', 'period', 'version__school_class')

    if school_class is not None:
        lessons = lessons.filter(version__school_class=school_class)

    substitutions = {
        (sub.school_class_id, sub.period_id): sub
        for sub in Substitution.objects.filter(date=day_date).select_related(
            'substitute_teacher', 'room')
    }

    rows = []
    for lesson in lessons:
        sub = substitutions.get((lesson.version.school_class_id, lesson.period_id))
        actual_teacher = lesson.teacher
        if sub and not sub.is_cancelled and sub.substitute_teacher_id:
            actual_teacher = sub.substitute_teacher
        row = {
            'lesson': lesson,
            'substitution': sub,
            'teacher': actual_teacher,
            'is_cancelled': bool(sub and sub.is_cancelled),
        }
        if teacher is not None and actual_teacher != teacher and lesson.teacher != teacher:
            continue
        rows.append(row)

    rows.sort(key=lambda r: (r['lesson'].period.start_time,
                             r['lesson'].version.school_class.name))
    return rows


def can_teach_on_date(user, school_class, period, day_date):
    """Учителят може да въвежда тема само за часове, по които е основен
    преподавател или назначен заместник за деня."""
    day_of_week = day_date.isoweekday()
    lesson = Lesson.objects.filter(
        version__school_class=school_class,
        version__status=TimetableVersion.PUBLISHED,
        day_of_week=day_of_week, period=period,
    ).select_related('subject').first()
    if lesson is None:
        return None

    sub = Substitution.objects.filter(
        date=day_date, school_class=school_class, period=period,
    ).first()
    if sub and sub.is_cancelled:
        return None
    if sub and sub.substitute_teacher_id:
        return lesson if sub.substitute_teacher_id == user.pk else None
    return lesson if lesson.teacher_id == user.pk else None


# ── Отсъствия и замествания ───────────────────────────────────

def absent_teacher_ids(day_date):
    return set(TeacherAbsence.objects.filter(
        status__in=BLOCKING_ABSENCE_STATUSES,
        start_date__lte=day_date, end_date__gte=day_date,
    ).values_list('teacher_id', flat=True))


def affected_lessons(absence, school_year):
    """Всички засегнати часове за периода на отсъствието — по дати."""
    rows = []
    day = absence.start_date
    end = min(absence.end_date, absence.start_date + timedelta(days=MAX_ABSENCE_DAYS))

    while day <= end:
        if day.isoweekday() in DAYS:
            lessons = Lesson.objects.filter(
                version__school_year=school_year,
                version__status=TimetableVersion.PUBLISHED,
                day_of_week=day.isoweekday(), teacher=absence.teacher,
            ).select_related('subject', 'room', 'period', 'version__school_class')

            for lesson in sorted(lessons, key=lambda l: l.period.start_time):
                sub = Substitution.objects.filter(
                    date=day, school_class=lesson.version.school_class,
                    period=lesson.period,
                ).select_related('substitute_teacher').first()
                rows.append({'date': day, 'lesson': lesson, 'substitution': sub})
        day += timedelta(days=1)
    return rows


def busy_teacher_ids(school_year, day_date, period, exclude_class=None):
    """Преподавателите, които вече имат час в този ден и период —
    по разписание или като назначени заместници.

    `exclude_class` пропуска часа на самия клас, за който търсим заместник —
    иначе вече назначеният заместник би излизал като зает от собствения си час.
    """
    day_of_week = day_date.isoweekday()
    lessons = Lesson.objects.filter(
        version__school_year=school_year,
        version__status=TimetableVersion.PUBLISHED,
        day_of_week=day_of_week, period=period,
    ).select_related('version__school_class')

    if exclude_class is not None:
        lessons = lessons.exclude(version__school_class=exclude_class)

    subs = {
        sub.school_class_id: sub
        for sub in Substitution.objects.filter(date=day_date, period=period)
    }

    busy = set()
    for lesson in lessons:
        sub = subs.get(lesson.version.school_class_id)
        if sub:
            if sub.is_cancelled:
                continue
            if sub.substitute_teacher_id:
                busy.add(sub.substitute_teacher_id)
                continue
        busy.add(lesson.teacher_id)
    return busy


def available_substitutes(school_year, day_date, period, subject,
                          exclude_teacher=None, school_class=None):
    """Свободните преподаватели за конкретен ден и час.
    Тези, които преподават същия предмет, са първи в списъка."""
    busy = busy_teacher_ids(school_year, day_date, period, exclude_class=school_class)
    absent = absent_teacher_ids(day_date)
    if exclude_teacher is not None:
        busy.add(exclude_teacher.pk)

    same_subject = set(TeacherClassSubject.objects.filter(
        subject=subject).values_list('teacher_id', flat=True))

    candidates = User.objects.filter(role='teacher', is_active=True).exclude(
        pk__in=busy | absent
    ).order_by('first_name', 'last_name')

    return sorted(
        [{'teacher': t, 'teaches_subject': t.pk in same_subject} for t in candidates],
        key=lambda row: (not row['teaches_subject'], row['teacher'].first_name),
    )


def check_substitute(school_year, day_date, period, substitute,
                     original_teacher=None, school_class=None):
    """Заместникът трябва да е свободен и да не е отбелязан като отсъстващ."""
    errors = []
    if original_teacher is not None and substitute.pk == original_teacher.pk:
        errors.append('Заместникът не може да е основният преподавател.')
    if substitute.pk in absent_teacher_ids(day_date):
        errors.append(f'{substitute.get_full_name()} е отбелязан(а) като отсъстващ(а) на тази дата.')
    if substitute.pk in busy_teacher_ids(
        school_year, day_date, period, exclude_class=school_class
    ):
        errors.append(
            f'{substitute.get_full_name()} вече има час в {period.number}. час на тази дата.'
        )
    return errors


# ── Известяване по имейл ──────────────────────────────────────

def notify_lesson_change(lesson, day_date, kind, substitute_teacher=None, note=''):
    """Известява по имейл учениците и родителите от засегнатия клас при
    отмяна на час или назначаване на заместник за конкретна дата.

    `kind` е 'cancelled' или 'substituted'. Текстът е един и същ за целия
    клас, затова се изпраща едно писмо с всички получатели в BCC — не по
    едно писмо на всеки ученик. Изпращане по едно писмо на получател
    отваря отделна SMTP връзка всеки път (MAIL FROM/RCPT TO/DATA), което
    при клас с 25+ ученика отнема над 20 секунди в самата HTTP заявка;
    едно писмо с всички в BCC отнема около 2 секунди. BCC пази имейлите
    на семействата скрити едно от друго.
    """
    from django.core.mail import EmailMessage
    from django.conf import settings
    from students.models import StudentProfile

    day_label = f'{day_date:%d.%m.%Y}'
    time_label = f'{lesson.period.start_time:%H:%M}–{lesson.period.end_time:%H:%M}'

    if kind == 'cancelled':
        subject_line = f'Отменен час — {lesson.subject} ({lesson.version.school_class})'
        detail = (
            f'Часът по {lesson.subject} на {day_label} '
            f'({lesson.period.number}. час, {time_label}) за клас '
            f'{lesson.version.school_class} е отменен.'
        )
        if note:
            detail += f'\nПричина: {note}'
    else:
        subject_line = f'Промяна в разписанието — {lesson.subject} ({lesson.version.school_class})'
        detail = (
            f'Часът по {lesson.subject} на {day_label} '
            f'({lesson.period.number}. час, {time_label}) за клас '
            f'{lesson.version.school_class} ще бъде преподаден от '
            f'{substitute_teacher.get_full_name()} вместо {lesson.teacher.get_full_name()}.'
        )

    students = StudentProfile.objects.filter(
        school_class=lesson.version.school_class
    ).select_related('user').prefetch_related('parents__user')

    recipients = []
    for student in students:
        if student.user.email:
            recipients.append(student.user.email)
        recipients += [p.user.email for p in student.parents.all() if p.user.email]
    # Премахва дубликати (напр. ако двама родители по грешка имат един и
    # същ адрес), без да разбърква реда.
    recipients = list(dict.fromkeys(recipients))
    if not recipients:
        return

    email = EmailMessage(
        subject=subject_line,
        body=f'Здравейте,\n\n{detail}\n\nС уважение,\nEduNova',
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[settings.DEFAULT_FROM_EMAIL],
        bcc=recipients,
    )
    email.send(fail_silently=True)
