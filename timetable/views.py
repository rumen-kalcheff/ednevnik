"""Административни изгледи за учебното разписание.

Изгледите за учител, ученик и родител са в съответните приложения —
както при оценките и материалите.
"""

import datetime

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib import messages
from django.db.models import Count

from accounts.models import User
from accounts.decorators import role_required
from school.models import Class, Subject, TeacherClassSubject
from . import services
from .models import (
    ClassYearSetting, CurriculumEntry, Lesson, Period, Room, SchoolYear,
    Shift, Substitution, TeacherAbsence, TimetableLog, TimetableVersion,
)


def _current_year(request):
    """Учебната година, с която се работи (по подразбиране текущата)."""
    year_id = request.GET.get('year') or request.POST.get('year')
    if year_id:
        return SchoolYear.objects.filter(pk=year_id).first() or SchoolYear.current()
    return SchoolYear.current()


def _parse_date(raw, default=None):
    try:
        return datetime.date.fromisoformat(raw)
    except (TypeError, ValueError):
        return default or datetime.date.today()


# ── Табло на разписанието ─────────────────────────────────────

@role_required('admin')
def dashboard(request):
    year = _current_year(request)
    classes = Class.objects.filter(is_active=True)

    rows = []
    for school_class in classes:
        setting = services.class_setting(year, school_class) if year else None
        rows.append({
            'school_class': school_class,
            'setting': setting,
            'draft': services.draft_version(year, school_class) if year else None,
            'published': services.published_version(year, school_class) if year else None,
        })

    return render(request, 'timetable/dashboard.html', {
        'year': year,
        'years': SchoolYear.objects.all(),
        'rows': rows,
        'room_count': Room.objects.filter(is_active=True).count(),
        'pending_absences': TeacherAbsence.objects.filter(
            status=TeacherAbsence.PENDING).count(),
    })


# ── Учебни години, смени и периоди ────────────────────────────

@role_required('admin')
def settings_view(request):
    year = _current_year(request)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add_year':
            name = request.POST.get('name', '').strip()
            if not name:
                messages.error(request, 'Въведете наименование на учебната година.')
            elif SchoolYear.objects.filter(name=name).exists():
                messages.error(request, 'Тази учебна година вече съществува.')
            else:
                SchoolYear.objects.create(name=name, is_current=True)
                TimetableLog.log(request.user, 'settings', f'Създадена учебна година {name}')
                messages.success(request, f'Учебна година {name} е създадена и е текуща.')
            return redirect('timetable_settings')

        if action == 'set_current_year':
            selected = get_object_or_404(SchoolYear, pk=request.POST.get('school_year'))
            selected.is_current = True
            selected.save()
            messages.success(request, f'Текуща учебна година: {selected}.')
            return redirect('timetable_settings')

        if action == 'add_shift':
            name = request.POST.get('name', '').strip()
            order = request.POST.get('order') or 1
            if not name:
                messages.error(request, 'Въведете наименование на смяната.')
            elif Shift.objects.filter(name=name).exists():
                messages.error(request, 'Смяна с това име вече съществува.')
            else:
                Shift.objects.create(name=name, order=order)
                TimetableLog.log(request.user, 'settings', f'Създадена смяна {name}')
                messages.success(request, f'Смяна {name} е създадена.')
            return redirect('timetable_settings')

        if action == 'save_periods':
            shift = get_object_or_404(Shift, pk=request.POST.get('shift'))
            saved = 0
            for period in shift.periods.all():
                start = request.POST.get(f'start_{period.pk}')
                end = request.POST.get(f'end_{period.pk}')
                if not start or not end:
                    continue
                if start >= end:
                    messages.error(
                        request, f'{period.number}. час: началният час трябва да е преди крайния.')
                    continue
                period.start_time = start
                period.end_time = end
                period.save(update_fields=['start_time', 'end_time'])
                saved += 1
            TimetableLog.log(request.user, 'settings', f'Променени часовете на {shift}')
            messages.success(request, f'Записани промени по {saved} учебни периода.')
            return redirect('timetable_settings')

        if action == 'add_period':
            shift = get_object_or_404(Shift, pk=request.POST.get('shift'))
            number = request.POST.get('number')
            start = request.POST.get('start_time')
            end = request.POST.get('end_time')
            if not (number and start and end):
                messages.error(request, 'Попълнете пореден номер, начален и краен час.')
            elif start >= end:
                messages.error(request, 'Началният час трябва да е преди крайния.')
            elif shift.periods.filter(number=number).exists():
                messages.error(request, f'{shift} вече има {number}. час.')
            else:
                Period.objects.create(shift=shift, number=number, start_time=start, end_time=end)
                messages.success(request, f'{number}. час е добавен към {shift}.')
            return redirect('timetable_settings')

        if action == 'delete_period':
            period = get_object_or_404(Period, pk=request.POST.get('period'))
            if period.lessons.exists():
                messages.error(request, 'Периодът участва в разписание и не може да бъде изтрит.')
            else:
                period.delete()
                messages.success(request, 'Учебният период е изтрит.')
            return redirect('timetable_settings')

    return render(request, 'timetable/settings.html', {
        'year': year,
        'years': SchoolYear.objects.all(),
        'shifts': Shift.objects.prefetch_related('periods').all(),
    })


# ── Учебни зали ───────────────────────────────────────────────

@role_required('admin')
def room_list(request):
    rooms = Room.objects.annotate(lesson_count=Count('lessons')).all()
    return render(request, 'timetable/room_list.html', {
        'rooms': rooms,
        'room_types': Room.ROOM_TYPE_CHOICES,
    })


@role_required('admin')
def room_create(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            messages.error(request, 'Въведете номер или наименование на залата.')
        elif Room.objects.filter(name=name).exists():
            messages.error(request, 'Зала с това наименование вече съществува.')
        else:
            Room.objects.create(
                name=name,
                capacity=request.POST.get('capacity') or 26,
                room_type=request.POST.get('room_type', 'standard'),
                is_active=bool(request.POST.get('is_active')),
            )
            messages.success(request, f'Зала {name} е създадена.')
            return redirect('room_list')

    return render(request, 'timetable/room_form.html', {
        'action': 'Създай', 'room_types': Room.ROOM_TYPE_CHOICES,
    })


@role_required('admin')
def room_edit(request, pk):
    room = get_object_or_404(Room, pk=pk)
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if Room.objects.filter(name=name).exclude(pk=room.pk).exists():
            messages.error(request, 'Зала с това наименование вече съществува.')
        else:
            room.name = name
            room.capacity = request.POST.get('capacity') or room.capacity
            room.room_type = request.POST.get('room_type', room.room_type)
            room.is_active = bool(request.POST.get('is_active'))
            room.save()
            messages.success(request, 'Залата е актуализирана.')
            return redirect('room_list')

    return render(request, 'timetable/room_form.html', {
        'action': 'Редактирай', 'obj': room, 'room_types': Room.ROOM_TYPE_CHOICES,
    })


@role_required('admin')
def room_delete(request, pk):
    """Зала, която участва в разписание, не се изтрива физически, а се деактивира."""
    room = get_object_or_404(Room, pk=pk)
    if request.method == 'POST':
        if room.lessons.exists() or room.substitutions.exists():
            room.is_active = False
            room.save(update_fields=['is_active'])
            messages.warning(
                request, f'Зала {room} участва в разписание — вместо изтриване е деактивирана.')
        else:
            room.delete()
            messages.success(request, 'Залата е изтрита.')
        return redirect('room_list')
    return render(request, 'adminpanel/confirm_delete.html', {'obj': room, 'type': 'учебна зала'})


# ── Смени и чужди езици по класове ────────────────────────────

@role_required('admin')
def class_settings(request):
    year = _current_year(request)
    if year is None:
        messages.error(request, 'Създайте учебна година от настройките.')
        return redirect('timetable_settings')

    if request.method == 'POST':
        school_class = get_object_or_404(Class, pk=request.POST.get('school_class'))
        shift = get_object_or_404(Shift, pk=request.POST.get('shift'))
        first_id = request.POST.get('first_language') or None
        second_id = request.POST.get('second_language') or None

        if first_id and second_id and first_id == second_id:
            messages.error(request, 'Първият и вторият чужд език не могат да съвпадат.')
            return redirect(f'{request.path}?year={year.pk}')

        setting, _ = ClassYearSetting.objects.update_or_create(
            school_year=year, school_class=school_class,
            defaults={'shift': shift, 'first_language_id': first_id,
                      'second_language_id': second_id},
        )
        # Часовете извън новата смяна остават невалидни — предупреждаваме.
        wrong = Lesson.objects.filter(
            version__school_year=year, version__school_class=school_class,
        ).exclude(period__shift=shift).count()
        if wrong:
            messages.warning(
                request, f'{wrong} часа в разписанието на {school_class} остават извън {shift}.')

        TimetableLog.log(request.user, 'settings',
                         f'Настройки на {school_class}: {shift}, '
                         f'{setting.first_language} / {setting.second_language}')
        messages.success(request, f'Настройките на клас {school_class} са записани.')
        return redirect(f'{request.path}?year={year.pk}')

    settings_by_class = {
        s.school_class_id: s
        for s in ClassYearSetting.objects.filter(school_year=year).select_related(
            'shift', 'first_language', 'second_language')
    }
    rows = [
        {'school_class': school_class, 'setting': settings_by_class.get(school_class.pk)}
        for school_class in Class.objects.filter(is_active=True)
    ]

    return render(request, 'timetable/class_settings.html', {
        'year': year, 'years': SchoolYear.objects.all(), 'rows': rows,
        'shifts': Shift.objects.filter(is_active=True),
        'languages': Subject.objects.filter(is_foreign_language=True, is_active=True),
    })


# ── Седмичен хорариум ─────────────────────────────────────────

@role_required('admin')
def curriculum(request):
    year = _current_year(request)
    if year is None:
        messages.error(request, 'Създайте учебна година от настройките.')
        return redirect('timetable_settings')

    classes = Class.objects.filter(is_active=True)
    class_id = request.GET.get('class') or request.POST.get('school_class')
    school_class = get_object_or_404(Class, pk=class_id) if class_id else classes.first()

    if request.method == 'POST' and school_class:
        action = request.POST.get('action')

        if action == 'delete':
            entry = get_object_or_404(CurriculumEntry, pk=request.POST.get('entry'))
            placed = Lesson.objects.filter(
                version__school_year=year, version__school_class=entry.school_class,
                version__status__in=[TimetableVersion.DRAFT, TimetableVersion.PUBLISHED],
                subject=entry.subject,
            ).count()
            if placed:
                messages.error(
                    request,
                    f'{entry.subject} е поставен(а) {placed} пъти в разписанието — '
                    f'първо премахнете часовете.')
            else:
                entry.delete()
                messages.success(request, 'Редът е премахнат от хорариума.')
        else:
            subject_id = request.POST.get('subject')
            hours = request.POST.get('hours_per_week')
            if not subject_id or not hours or not str(hours).isdigit() or int(hours) < 1:
                messages.error(request, 'Изберете предмет и въведете брой часове (поне 1).')
            else:
                CurriculumEntry.objects.update_or_create(
                    school_year=year, school_class=school_class, subject_id=subject_id,
                    defaults={'hours_per_week': hours},
                )
                TimetableLog.log(request.user, 'settings',
                                 f'Хорариум {school_class}: предмет {subject_id} — {hours} ч.')
                messages.success(request, 'Хорариумът е записан.')
        return redirect(f'{request.path}?class={school_class.pk}&year={year.pk}')

    entries = []
    setting = None
    if school_class:
        setting = services.class_setting(year, school_class)
        # Броим часовете от версията, с която се работи — черновата, ако има.
        version = services.working_version(year, school_class)
        placed = dict(Lesson.objects.filter(version=version).values_list(
            'subject').annotate(n=Count('pk'))) if version else {}

        for entry in CurriculumEntry.objects.filter(
            school_year=year, school_class=school_class
        ).select_related('subject'):
            entries.append({'entry': entry, 'placed': placed.get(entry.subject_id, 0)})

    # Предмети, които класът може да изучава — тези с назначен преподавател.
    available_subjects = Subject.objects.filter(
        is_active=True, assignments__school_class=school_class,
    ).distinct() if school_class else Subject.objects.none()

    total_hours = sum(row['entry'].hours_per_week for row in entries)

    return render(request, 'timetable/curriculum.html', {
        'year': year, 'years': SchoolYear.objects.all(),
        'classes': classes, 'school_class': school_class, 'setting': setting,
        'entries': entries, 'subjects': available_subjects, 'total_hours': total_hours,
    })


# ── Решетка на разписанието ───────────────────────────────────

@role_required('admin')
def grid(request):
    year = _current_year(request)
    if year is None:
        messages.error(request, 'Създайте учебна година от настройките.')
        return redirect('timetable_settings')

    classes = Class.objects.filter(is_active=True)
    class_id = request.GET.get('class')
    school_class = get_object_or_404(Class, pk=class_id) if class_id else None

    context = {
        'year': year, 'years': SchoolYear.objects.all(),
        'classes': classes, 'school_class': school_class,
        'days': [(day, services.DAY_NAMES[day]) for day in services.DAYS],
    }

    if school_class is None:
        return render(request, 'timetable/grid.html', context)

    setting = services.class_setting(year, school_class)
    periods = services.class_periods(year, school_class)
    draft = services.draft_version(year, school_class)
    published = services.published_version(year, school_class)
    version = draft or published

    # Колко часа по предмет са поставени спрямо хорариума.
    placed = dict(Lesson.objects.filter(version=version).values_list(
        'subject').annotate(n=Count('pk'))) if version else {}
    progress = [
        {'entry': entry, 'placed': placed.get(entry.subject_id, 0),
         'missing': entry.hours_per_week - placed.get(entry.subject_id, 0)}
        for entry in CurriculumEntry.objects.filter(
            school_year=year, school_class=school_class).select_related('subject')
    ]

    context.update({
        'setting': setting, 'periods': periods,
        'draft': draft, 'published': published, 'version': version,
        'rows': services.week_grid(version, periods),
        'progress': progress,
        'total_required': sum(row['entry'].hours_per_week for row in progress),
        'total_placed': sum(row['placed'] for row in progress),
    })
    return render(request, 'timetable/grid.html', context)


@role_required('admin')
def start_editing(request, pk):
    """Създава чернова (копие на публикуваното) за редакция."""
    school_class = get_object_or_404(Class, pk=pk)
    year = _current_year(request)
    if year is None:
        messages.error(request, 'Създайте учебна година от настройките.')
        return redirect('timetable_settings')

    if request.method == 'POST':
        services.get_or_create_draft(year, school_class, request.user)
        TimetableLog.log(request.user, 'settings', f'Отворена чернова за {school_class}')
        messages.info(
            request,
            f'Работите върху чернова на разписанието за {school_class}. '
            f'Промените стават видими за учители, ученици и родители след публикуване.')
    return redirect(f'{_grid_url()}?class={school_class.pk}&year={year.pk}')


@role_required('admin')
def discard_draft(request, pk):
    version = get_object_or_404(TimetableVersion, pk=pk, status=TimetableVersion.DRAFT)
    school_class = version.school_class
    if request.method == 'POST':
        version.delete()
        TimetableLog.log(request.user, 'settings', f'Отказана чернова за {school_class}')
        messages.success(request, f'Черновата за {school_class} е премахната.')
        return redirect(f"{_grid_url()}?class={school_class.pk}")
    return render(request, 'adminpanel/confirm_delete.html', {
        'obj': f'черновата на разписанието за {school_class}', 'type': 'чернова',
    })


@role_required('admin')
def publish_version(request, pk):
    version = get_object_or_404(TimetableVersion, pk=pk, status=TimetableVersion.DRAFT)
    if request.method == 'POST':
        errors = services.publish(version, request.user)
        if errors:
            messages.error(request, 'Разписанието не може да бъде публикувано:')
            for error in errors:
                messages.error(request, error)
        else:
            TimetableLog.log(request.user, 'publish',
                             f'Публикувано разписание за {version.school_class}')
            messages.success(
                request, f'Разписанието на {version.school_class} е публикувано.')
    return redirect(f"{_grid_url()}?class={version.school_class_id}&year={version.school_year_id}")


def _grid_url():
    return reverse('timetable_grid')


# ── Час от разписанието ───────────────────────────────────────

@role_required('admin')
def lesson_add(request):
    year = _current_year(request)
    class_id = request.GET.get('class') or request.POST.get('school_class')
    if not class_id:
        messages.error(request, 'Изберете клас.')
        return redirect('timetable_grid')

    school_class = get_object_or_404(Class, pk=class_id)
    setting = services.class_setting(year, school_class)
    periods = services.class_periods(year, school_class)

    if request.method == 'POST':
        draft = services.get_or_create_draft(year, school_class, request.user)
        errors = _save_lesson(request, draft, lesson=None)
        if not errors:
            return redirect(f"{_grid_url()}?class={school_class.pk}&year={year.pk}")
        for error in errors:
            messages.error(request, error)

    return render(request, 'timetable/lesson_form.html', {
        'action': 'Добави', 'year': year, 'school_class': school_class,
        'setting': setting, 'periods': periods,
        'days': [(day, services.DAY_NAMES[day]) for day in services.DAYS],
        'selected_day': request.GET.get('day') or request.POST.get('day_of_week'),
        'selected_period': request.GET.get('period') or request.POST.get('period'),
        **_lesson_choices(year, school_class),
    })


@role_required('admin')
def lesson_edit(request, pk):
    lesson = get_object_or_404(Lesson.objects.select_related(
        'version__school_class', 'period', 'subject', 'teacher', 'room'), pk=pk)
    version = lesson.version
    school_class = version.school_class
    year = version.school_year

    if not version.is_draft:
        messages.error(request, 'Редактира се само чернова. Отворете разписанието за редакция.')
        return redirect(f"{_grid_url()}?class={school_class.pk}&year={year.pk}")

    if request.method == 'POST':
        errors = _save_lesson(request, version, lesson=lesson)
        if not errors:
            return redirect(f"{_grid_url()}?class={school_class.pk}&year={year.pk}")
        for error in errors:
            messages.error(request, error)

    return render(request, 'timetable/lesson_form.html', {
        'action': 'Запази', 'year': year, 'school_class': school_class,
        'obj': lesson, 'setting': services.class_setting(year, school_class),
        'periods': services.class_periods(year, school_class),
        'days': [(day, services.DAY_NAMES[day]) for day in services.DAYS],
        'selected_day': request.POST.get('day_of_week') or lesson.day_of_week,
        'selected_period': request.POST.get('period') or lesson.period_id,
        **_lesson_choices(year, school_class),
    })


def _lesson_choices(year, school_class):
    """Предметите от хорариума и преподавателите с право да ги преподават."""
    entries = CurriculumEntry.objects.filter(
        school_year=year, school_class=school_class,
    ).select_related('subject')
    assignments = TeacherClassSubject.objects.filter(
        school_class=school_class,
        subject__in=[entry.subject_id for entry in entries],
    ).select_related('teacher', 'subject')

    return {
        'subjects': [entry.subject for entry in entries],
        'assignments': assignments,
        'rooms': Room.objects.filter(is_active=True),
    }


def _save_lesson(request, version, lesson=None):
    """Обща логика за добавяне и редакция — с всички сървърни проверки."""
    day_of_week = request.POST.get('day_of_week')
    period_id = request.POST.get('period')
    subject_id = request.POST.get('subject')
    teacher_id = request.POST.get('teacher')
    room_id = request.POST.get('room')

    if not all([day_of_week, period_id, subject_id, teacher_id, room_id]):
        return ['Попълнете всички полета.']

    period = get_object_or_404(Period, pk=period_id)
    subject = get_object_or_404(Subject, pk=subject_id)
    teacher = get_object_or_404(User, pk=teacher_id, role='teacher')
    room = get_object_or_404(Room, pk=room_id)
    day_of_week = int(day_of_week)

    errors = services.check_lesson(
        version, day_of_week, period, subject, teacher, room, exclude_lesson=lesson)
    errors += services.check_curriculum_capacity(version, subject, exclude_lesson=lesson)
    if errors:
        return errors

    if lesson is None:
        lesson = Lesson.objects.create(
            version=version, day_of_week=day_of_week, period=period,
            subject=subject, teacher=teacher, room=room,
        )
        TimetableLog.log(request.user, 'lesson_create', str(lesson))
        messages.success(request, 'Часът е добавен в черновата.')
    else:
        lesson.day_of_week = day_of_week
        lesson.period = period
        lesson.subject = subject
        lesson.teacher = teacher
        lesson.room = room
        lesson.save()
        TimetableLog.log(request.user, 'lesson_update', str(lesson))
        messages.success(request, 'Часът е променен.')
    return []


@role_required('admin')
def lesson_delete(request, pk):
    lesson = get_object_or_404(Lesson.objects.select_related(
        'version__school_class', 'subject', 'period'), pk=pk)
    school_class = lesson.version.school_class

    if not lesson.version.is_draft:
        messages.error(request, 'Изтрива се само от чернова. Отворете разписанието за редакция.')
        return redirect(f"{_grid_url()}?class={school_class.pk}")

    if request.method == 'POST':
        TimetableLog.log(request.user, 'lesson_delete', str(lesson))
        lesson.delete()
        messages.success(request, 'Часът е премахнат от разписанието.')
        return redirect(f"{_grid_url()}?class={school_class.pk}")

    return render(request, 'adminpanel/confirm_delete.html', {
        'obj': lesson, 'type': 'час от разписанието',
    })


# ── Разписание по преподавател ────────────────────────────────

@role_required('admin')
def teacher_grid(request):
    year = _current_year(request)
    teachers = User.objects.filter(role='teacher', is_active=True).order_by(
        'first_name', 'last_name')
    teacher_id = request.GET.get('teacher')
    teacher = get_object_or_404(User, pk=teacher_id, role='teacher') if teacher_id else None

    rows = services.teacher_week_grid(year, teacher) if (teacher and year) else []
    return render(request, 'timetable/teacher_grid.html', {
        'year': year, 'teachers': teachers, 'teacher': teacher, 'rows': rows,
        'days': [(day, services.DAY_NAMES[day]) for day in services.DAYS],
        'lesson_count': sum(1 for row in rows for cell in row['cells'] if cell['lesson']),
    })


# ── Отсъствия на преподаватели ────────────────────────────────

@role_required('admin')
def absence_list(request):
    year = _current_year(request)
    status = request.GET.get('status', '')

    if request.method == 'POST':
        if not request.POST.get('teacher'):
            messages.error(request, 'Изберете преподавател.')
            return redirect('teacher_absence_list')

        teacher = get_object_or_404(User, pk=request.POST.get('teacher'), role='teacher')
        start = _parse_date(request.POST.get('start_date'))
        end = _parse_date(request.POST.get('end_date'), start)
        if end < start:
            messages.error(request, 'Крайната дата не може да е преди началната.')
        else:
            absence = TeacherAbsence.objects.create(
                teacher=teacher, start_date=start, end_date=end,
                reason=request.POST.get('reason', '').strip(),
                status=TeacherAbsence.APPROVED, created_by=request.user,
            )
            TimetableLog.log(request.user, 'absence', f'Регистрирано отсъствие: {absence}')
            messages.success(request, 'Отсъствието е регистрирано.')
            return redirect('teacher_absence_affected', pk=absence.pk)

    absences = TeacherAbsence.objects.select_related('teacher').all()
    if status:
        absences = absences.filter(status=status)

    return render(request, 'timetable/absence_list.html', {
        'year': year, 'absences': absences, 'selected_status': status,
        'statuses': TeacherAbsence.STATUS_CHOICES,
        'teachers': User.objects.filter(role='teacher', is_active=True).order_by(
            'first_name', 'last_name'),
        'today': datetime.date.today(),
    })


@role_required('admin')
def absence_status(request, pk):
    absence = get_object_or_404(TeacherAbsence, pk=pk)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in dict(TeacherAbsence.STATUS_CHOICES):
            absence.status = new_status
            absence.save(update_fields=['status'])
            TimetableLog.log(request.user, 'absence',
                             f'{absence} — {absence.get_status_display()}')
            messages.success(request, f'Статусът е променен на „{absence.get_status_display()}“.')
        else:
            messages.error(request, 'Невалиден статус.')
    return redirect('teacher_absence_list')


@role_required('admin')
def absence_delete(request, pk):
    absence = get_object_or_404(TeacherAbsence, pk=pk)
    if request.method == 'POST':
        absence.delete()
        messages.success(request, 'Отсъствието е изтрито.')
        return redirect('teacher_absence_list')
    return render(request, 'adminpanel/confirm_delete.html', {
        'obj': absence, 'type': 'отсъствие на преподавател',
    })


@role_required('admin')
def absence_affected(request, pk):
    """Засегнатите часове за периода на отсъствието и назначаване на заместник."""
    absence = get_object_or_404(TeacherAbsence.objects.select_related('teacher'), pk=pk)
    year = _current_year(request)
    rows = services.affected_lessons(absence, year) if year else []

    for row in rows:
        row['candidates'] = services.available_substitutes(
            year, row['date'], row['lesson'].period, row['lesson'].subject,
            exclude_teacher=absence.teacher,
            school_class=row['lesson'].version.school_class,
        )

    return render(request, 'timetable/absence_affected.html', {
        'absence': absence, 'rows': rows, 'year': year,
    })


# ── Замествания ───────────────────────────────────────────────

@role_required('admin')
def substitution_day(request):
    """Часовете за конкретна дата с назначените замествания."""
    year = _current_year(request)
    day = _parse_date(request.GET.get('date'))
    class_id = request.GET.get('class')
    school_class = get_object_or_404(Class, pk=class_id) if class_id else None

    rows = services.lessons_on_date(year, day, school_class=school_class) if year else []
    absent_ids = services.absent_teacher_ids(day)
    for row in rows:
        row['teacher_absent'] = row['lesson'].teacher_id in absent_ids
        row['candidates'] = services.available_substitutes(
            year, day, row['lesson'].period, row['lesson'].subject,
            exclude_teacher=row['lesson'].teacher,
            school_class=row['lesson'].version.school_class,
        )

    return render(request, 'timetable/substitution_day.html', {
        'year': year, 'date': day, 'rows': rows,
        'classes': Class.objects.filter(is_active=True), 'school_class': school_class,
        'is_weekend': day.isoweekday() not in services.DAYS,
    })


@role_required('admin')
def substitution_save(request):
    """Назначава заместник, отменя час или премахва заместването —
    само за конкретна дата, без промяна на седмичното разписание."""
    if request.method != 'POST':
        return redirect('substitution_day')

    year = _current_year(request)
    lesson = get_object_or_404(Lesson.objects.select_related(
        'version__school_class', 'period', 'subject', 'teacher'),
        pk=request.POST.get('lesson'), version__status=TimetableVersion.PUBLISHED)
    day = _parse_date(request.POST.get('date'))
    action = request.POST.get('action')

    school_class = lesson.version.school_class
    common = {'date': day, 'school_class': school_class, 'period': lesson.period}

    if action == 'clear':
        Substitution.objects.filter(**common).delete()
        TimetableLog.log(request.user, 'substitution',
                         f'Премахнато заместване: {school_class}, {day}, {lesson.period.number}. час')
        messages.success(request, 'Заместването е премахнато.')

    elif action == 'cancel':
        note = request.POST.get('note', '').strip()
        Substitution.objects.update_or_create(
            **common,
            defaults={'subject': lesson.subject, 'original_teacher': lesson.teacher,
                      'substitute_teacher': None, 'is_cancelled': True,
                      'note': note, 'created_by': request.user},
        )
        TimetableLog.log(request.user, 'substitution',
                         f'Отменен час: {school_class}, {day}, {lesson.period.number}. час')
        services.notify_lesson_change(lesson, day, 'cancelled', note=note)
        messages.warning(request, f'Часът на {school_class} за {day:%d.%m.%Y} е отменен.')

    elif not request.POST.get('substitute_teacher'):
        messages.error(request, 'Изберете заместник от списъка.')

    else:
        substitute = get_object_or_404(
            User, pk=request.POST.get('substitute_teacher'), role='teacher')
        errors = services.check_substitute(
            year, day, lesson.period, substitute,
            original_teacher=lesson.teacher, school_class=school_class)
        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            Substitution.objects.update_or_create(
                **common,
                defaults={'subject': lesson.subject, 'original_teacher': lesson.teacher,
                          'substitute_teacher': substitute, 'is_cancelled': False,
                          'room': lesson.room,
                          'note': request.POST.get('note', '').strip(),
                          'created_by': request.user},
            )
            TimetableLog.log(
                request.user, 'substitution',
                f'{substitute.get_full_name()} замества {lesson.teacher.get_full_name()} — '
                f'{school_class}, {day}, {lesson.period.number}. час')
            services.notify_lesson_change(
                lesson, day, 'substituted', substitute_teacher=substitute)
            messages.success(
                request,
                f'{substitute.get_full_name()} ще замести {lesson.teacher.get_full_name()} '
                f'на {day:%d.%m.%Y}, {lesson.period.number}. час.')

    # Връщаме се там, откъдето е дошла заявката (списък по дата или отсъствие).
    back = request.POST.get('next', '')
    if back.startswith('/'):
        return redirect(back)
    return redirect(f"{reverse('substitution_day')}?date={day.isoformat()}")


# ── Дневник на действията ─────────────────────────────────────

@role_required('admin')
def log_list(request):
    action = request.GET.get('action', '')
    logs = TimetableLog.objects.select_related('user').all()
    if action:
        logs = logs.filter(action=action)
    return render(request, 'timetable/log_list.html', {
        'logs': logs[:300], 'actions': TimetableLog.ACTION_CHOICES, 'selected_action': action,
    })
