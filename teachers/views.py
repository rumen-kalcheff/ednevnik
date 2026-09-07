from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.http import JsonResponse
from django.contrib import messages
from django.db.models import Avg
from collections import Counter
from itertools import groupby
from datetime import date
from accounts.decorators import role_required
from school.models import TeacherClassSubject
from students.models import StudentProfile
from grades.models import Grade, Absence
from materials.models import Material


def _teacher_assignments(user):
    return TeacherClassSubject.objects.filter(teacher=user).select_related('school_class', 'subject')


def _teacher_class_subject_options(user, day):
    """(клас, предмет) двойки, за които учителят може да въвежда отсъствия на `day`.

    За класове с публикувано разписание се разрешават само реални часове на
    учителя за тази дата (вкл. часове, в които е назначен заместник за деня;
    отменените часове и тези, от които е свален чрез заместване, отпадат).
    За класове без въведено разписание (няма данни за проверка) се разрешават
    постоянните му назначения без ограничение по дата."""
    from timetable import services
    from timetable.models import SchoolYear, TimetableVersion

    year = SchoolYear.current()
    scheduled_class_ids = set(
        TimetableVersion.objects.filter(
            school_year=year, status=TimetableVersion.PUBLISHED,
        ).values_list('school_class_id', flat=True)
    ) if year else set()

    options = {}
    for a in _teacher_assignments(user):
        if a.school_class_id not in scheduled_class_ids:
            options[(a.school_class_id, a.subject_id)] = (a.school_class, a.subject)

    if year:
        for row in services.lessons_on_date(year, day, teacher=user):
            if row['is_cancelled'] or row['teacher'] != user:
                continue
            lesson = row['lesson']
            key = (lesson.version.school_class_id, lesson.subject_id)
            options.setdefault(key, (lesson.version.school_class, lesson.subject))
    return options


def _homeroom_class(user):
    """Класът, на който потребителят е класен ръководител, или None."""
    from school.models import Class
    try:
        return user.homeroom_class
    except Class.DoesNotExist:
        return None


# Максимален брой текущи (нефинални) оценки на ученик за предмет.
MAX_CURRENT_GRADES = 15


# ── Оценки ───────────────────────────────────────────────────

@role_required('teacher')
def grade_list(request):
    assignments = _teacher_assignments(request.user)
    class_id = request.GET.get('class')
    subject_id = request.GET.get('subject')

    # Кои назначения (клас+предмет) да покажем спрямо филтрите.
    shown = assignments
    if class_id:
        shown = shown.filter(school_class_id=class_id)
    if subject_id:
        shown = shown.filter(subject_id=subject_id)

    # Една секция на клас+предмет; вътре — един ред на ученик с всичките му оценки.
    sections = []
    for a in shown.order_by('school_class__name', 'subject__name'):
        students = StudentProfile.objects.filter(
            school_class=a.school_class
        ).select_related('user').order_by('user__first_name', 'user__last_name')

        by_student = {}
        grades = Grade.objects.filter(
            teacher=request.user, subject=a.subject,
            student__school_class=a.school_class,
        ).order_by('pk')
        for g in grades:
            by_student.setdefault(g.student_id, []).append(g)

        rows = []
        for s in students:
            sgrades = by_student.get(s.pk, [])
            finals = {g.grade_type: g for g in sgrades if g.grade_type in Grade.FINAL_TYPES}
            current = [g for g in sgrades if g.grade_type not in Grade.FINAL_TYPES]
            rows.append({'student': s, 'grades': current, 'finals': finals})

        sections.append({
            'school_class': a.school_class, 'subject': a.subject, 'rows': rows,
        })

    classes = [a.school_class for a in assignments]
    subjects = [a.subject for a in assignments]

    return render(request, 'teachers/grade_list.html', {
        'sections': sections, 'classes': classes, 'subjects': subjects,
        'selected_class': class_id, 'selected_subject': subject_id,
    })


@role_required('teacher')
def grade_add(request):
    assignments = _teacher_assignments(request.user)
    classes = list({a.school_class for a in assignments})
    subjects = list({a.subject for a in assignments})

    if request.method == 'POST':
        student_id = request.POST.get('student')
        subject_id = request.POST.get('subject')
        value = request.POST.get('value')
        grade_type = request.POST.get('grade_type')
        grade_date = request.POST.get('date') or date.today()
        note = request.POST.get('note', '')

        from datetime import date as date_type
        import datetime
        if isinstance(grade_date, str):
            grade_date_obj = datetime.date.fromisoformat(grade_date)
        else:
            grade_date_obj = grade_date

        if grade_date_obj > date.today():
            messages.error(request, 'Датата не може да бъде в бъдещето.')
        else:
            Grade.objects.create(
                student_id=student_id, subject_id=subject_id,
                teacher=request.user, value=value,
                grade_type=grade_type, date=grade_date, note=note,
            )
            messages.success(request, 'Оценката е записана.')
            return redirect('grade_list')

    return render(request, 'teachers/grade_form.html', {
        'classes': classes, 'subjects': subjects,
        'grade_types': Grade.GRADE_TYPE_CHOICES,
        'grade_values': Grade.GRADE_VALUES,
        'today': date.today(),
    })


@role_required('teacher')
def grade_bulk(request):
    """Бързо въвеждане на оценки за цял клас по избран предмет."""
    import datetime
    assignments = _teacher_assignments(request.user)
    classes = list({a.school_class for a in assignments})
    subjects = list({a.subject for a in assignments})

    class_id = request.GET.get('class') or request.POST.get('class') or ''
    subject_id = request.GET.get('subject') or request.POST.get('subject') or ''

    # Позволени са само комбинации клас+предмет, за които учителят е назначен.
    valid = bool(class_id and subject_id and assignments.filter(
        school_class_id=class_id, subject_id=subject_id).exists())

    students = []
    if valid:
        students = list(StudentProfile.objects.filter(
            school_class_id=class_id
        ).select_related('user').order_by('user__first_name', 'user__last_name'))

    if request.method == 'POST':
        if not valid:
            messages.error(request, 'Нямате назначение за този клас и предмет.')
            return redirect('grade_bulk')

        # Изтриване на единична оценка (inline от таблицата).
        delete_id = request.POST.get('delete_grade')
        if delete_id:
            deleted, _ = Grade.objects.filter(
                pk=delete_id, teacher=request.user,
                subject_id=subject_id, student__school_class_id=class_id,
            ).delete()
            if deleted:
                messages.success(request, 'Оценката е изтрита.')
            else:
                messages.error(request, 'Оценката не беше намерена.')
            return redirect(f'{request.path}?class={class_id}&subject={subject_id}')

        grade_type = request.POST.get('grade_type')
        raw_date = request.POST.get('date') or str(date.today())
        try:
            grade_date = datetime.date.fromisoformat(raw_date)
        except ValueError:
            grade_date = date.today()

        if grade_type not in dict(Grade.GRADE_TYPE_CHOICES):
            messages.error(request, 'Невалиден вид оценка.')
        elif grade_date > date.today():
            messages.error(request, 'Датата не може да бъде в бъдещето.')
        else:
            is_final = grade_type in Grade.FINAL_TYPES
            # Текущ брой текущи (нефинални) оценки на ученик — за проверка на тавана.
            # Само собствените на учителя (таванът важи за неговите оценки).
            current_counts = Counter(
                Grade.objects.filter(
                    teacher=request.user,
                    subject_id=subject_id, student__school_class_id=class_id,
                ).exclude(grade_type__in=Grade.FINAL_TYPES).values_list('student_id', flat=True)
            )
            created = updated = skipped = limit_hit = 0
            for s in students:
                val = request.POST.get(f'value_{s.pk}', '').strip()
                if not val:
                    continue
                if not (val.isdigit() and 2 <= int(val) <= 6):
                    skipped += 1
                    continue
                note = request.POST.get(f'note_{s.pk}', '').strip()
                if is_final:
                    # Срочна/годишна — само една на ученик/предмет: обновяваме съществуващата.
                    obj, was_created = Grade.objects.update_or_create(
                        student=s, subject_id=subject_id,
                        teacher=request.user, grade_type=grade_type,
                        defaults={'value': val, 'date': grade_date, 'note': note},
                    )
                    created += was_created
                    updated += not was_created
                else:
                    if current_counts[s.pk] >= MAX_CURRENT_GRADES:
                        limit_hit += 1
                        continue
                    Grade.objects.create(
                        student=s, subject_id=subject_id, teacher=request.user,
                        value=val, grade_type=grade_type, date=grade_date, note=note,
                    )
                    current_counts[s.pk] += 1
                    created += 1

            if created or updated:
                parts = []
                if created:
                    parts.append(f'{created} нови')
                if updated:
                    parts.append(f'{updated} обновени')
                messages.success(request, f'Записани оценки: {", ".join(parts)}.')
            else:
                messages.info(request, 'Не бяха въведени оценки.')
            if skipped:
                messages.warning(request, f'{skipped} невалидни стойности бяха пропуснати (позволени са 2–6).')
            if limit_hit:
                messages.warning(request, f'{limit_hit} ученик(ци) вече имат максимума от '
                                          f'{MAX_CURRENT_GRADES} текущи оценки — новите не бяха добавени.')
            return redirect(f'{request.path}?class={class_id}&subject={subject_id}')

    # Съществуващи оценки по избрания предмет, групирани по ученик.
    # Само собствените на учителя — както в grade_list/grade_edit/grade_delete,
    # за да съвпадат двата изгледа при предмет с повече от един учител.
    grades_by_student = {}
    if valid:
        existing = Grade.objects.filter(
            teacher=request.user,
            subject_id=subject_id, student__school_class_id=class_id,
        ).select_related('student').order_by('pk')
        for g in existing:
            grades_by_student.setdefault(g.student_id, []).append(g)

    # Прикачваме списъка с оценки и текущите срочни/годишни към всеки ученик.
    rows = []
    for s in students:
        sgrades = grades_by_student.get(s.pk, [])
        finals = {g.grade_type: g for g in sgrades if g.grade_type in Grade.FINAL_TYPES}
        current = [g for g in sgrades if g.grade_type not in Grade.FINAL_TYPES]
        rows.append({
            'student': s, 'grades': current, 'finals': finals,
            'at_limit': len(current) >= MAX_CURRENT_GRADES,
        })

    return render(request, 'teachers/grade_bulk.html', {
        'classes': classes, 'subjects': subjects,
        'selected_class': class_id, 'selected_subject': subject_id,
        'rows': rows, 'valid': valid,
        'grade_types': Grade.GRADE_TYPE_CHOICES,
        'grade_values': Grade.GRADE_VALUES,
        'max_current': MAX_CURRENT_GRADES,
        'today': date.today(),
    })


@role_required('teacher')
def grade_edit(request, pk):
    grade = get_object_or_404(Grade, pk=pk, teacher=request.user)
    if request.method == 'POST':
        grade.value = request.POST.get('value')
        grade.grade_type = request.POST.get('grade_type')
        grade.date = request.POST.get('date')
        grade.note = request.POST.get('note', '')
        grade.save()
        messages.success(request, 'Оценката е актуализирана.')
        return redirect('grade_list')

    return render(request, 'teachers/grade_edit_form.html', {
        'grade': grade,
        'grade_types': Grade.GRADE_TYPE_CHOICES,
        'grade_values': Grade.GRADE_VALUES,
    })


@role_required('teacher')
def grade_delete(request, pk):
    grade = get_object_or_404(Grade, pk=pk, teacher=request.user)
    if request.method == 'POST':
        grade.delete()
        messages.success(request, 'Оценката е изтрита.')
        return redirect('grade_list')
    return render(request, 'teachers/confirm_delete.html', {'obj': grade, 'type': 'оценка'})


# ── Отсъствия ─────────────────────────────────────────────────

@role_required('teacher')
def absence_list(request):
    assignments = _teacher_assignments(request.user)
    class_id = request.GET.get('class')
    subject_id = request.GET.get('subject')
    absence_type = request.GET.get('type')

    absences = Absence.objects.filter(teacher=request.user).select_related(
        'student__user', 'subject', 'student__school_class'
    ).order_by('student__school_class__name', '-date')
    if class_id:
        absences = absences.filter(student__school_class_id=class_id)
    if subject_id:
        absences = absences.filter(subject_id=subject_id)
    if absence_type in ('excused', 'unexcused'):
        absences = absences.filter(absence_type=absence_type)

    absence_groups = [
        {'school_class': school_class, 'absences': list(group)}
        for school_class, group in groupby(absences, key=lambda a: a.student.school_class)
    ]

    classes = sorted({a.school_class for a in assignments}, key=lambda c: c.name)
    subjects = sorted({a.subject for a in assignments}, key=lambda s: s.name)
    return render(request, 'teachers/absence_list.html', {
        'absence_groups': absence_groups, 'classes': classes, 'subjects': subjects,
        'selected_class': class_id, 'selected_subject': subject_id,
        'selected_type': absence_type,
    })


@role_required('teacher')
def absence_add(request):
    if request.method == 'POST':
        student_ids = request.POST.getlist('students')
        subject_id = request.POST.get('subject')
        absence_date = request.POST.get('date') or date.today()
        absence_type = request.POST.get('absence_type', 'unexcused')

        import datetime
        if isinstance(absence_date, str):
            absence_date_obj = datetime.date.fromisoformat(absence_date)
        else:
            absence_date_obj = absence_date

        options = _teacher_class_subject_options(request.user, absence_date_obj)
        students = StudentProfile.objects.filter(pk__in=student_ids).select_related('school_class')

        if absence_date_obj > date.today():
            messages.error(request, 'Датата не може да бъде в бъдещето.')
        elif not subject_id or not students or any(
            (s.school_class_id, int(subject_id)) not in options for s in students
        ):
            messages.error(
                request, 'Нямате право да въвеждате отсъствия за този клас по избрания предмет на тази дата.')
        else:
            from school.models import Subject
            from students.models import ParentProfile
            from django.core.mail import send_mail
            from django.conf import settings

            subject_obj = Subject.objects.get(pk=subject_id)
            absence_type_display = dict(Absence.ABSENCE_TYPE_CHOICES).get(absence_type, absence_type)

            for sid in student_ids:
                _, created = Absence.objects.get_or_create(
                    student_id=sid, subject_id=subject_id,
                    teacher=request.user, date=absence_date,
                    defaults={'absence_type': absence_type},
                )
                if created:
                    student = StudentProfile.objects.select_related('user').get(pk=sid)
                    parents = ParentProfile.objects.filter(
                        children=student
                    ).select_related('user')
                    parent_emails = [p.user.email for p in parents if p.user.email]
                    if parent_emails:
                        send_mail(
                            subject=f'Отсъствие на {student.user.get_full_name()}',
                            message=(
                                f'Уважаеми родителю,\n\n'
                                f'Вашето дете {student.user.get_full_name()} има записано отсъствие:\n\n'
                                f'Дата: {absence_date_obj.strftime("%d.%m.%Y")}\n'
                                f'Предмет: {subject_obj.name}\n'
                                f'Вид: {absence_type_display}\n'
                                f'Учител: {request.user.get_full_name()}\n\n'
                                f'С уважение,\nEduNova'
                            ),
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            recipient_list=parent_emails,
                            fail_silently=True,
                        )
            messages.success(request, 'Отсъствията са записани.')
            return redirect('absence_list')

    today = date.today()
    try:
        initial_date = date.fromisoformat(request.GET.get('date', '')) if request.GET.get('date') else today
    except ValueError:
        initial_date = today
    if initial_date > today:
        initial_date = today

    return render(request, 'teachers/absence_form.html', {
        'absence_types': Absence.ABSENCE_TYPE_CHOICES,
        'today': today,
        'initial_date': initial_date,
        'initial_class_id': request.GET.get('class_id', ''),
        'initial_subject_id': request.GET.get('subject_id', ''),
    })


@role_required('teacher')
def absence_edit(request, pk):
    absence = get_object_or_404(Absence, pk=pk, teacher=request.user)
    if request.method == 'POST':
        absence.absence_type = request.POST.get('absence_type')
        absence.save()
        messages.success(request, 'Отсъствието е актуализирано.')
        return redirect('absence_list')
    return render(request, 'teachers/absence_edit_form.html', {
        'absence': absence, 'absence_types': Absence.ABSENCE_TYPE_CHOICES,
    })


@role_required('teacher')
def absence_delete(request, pk):
    absence = get_object_or_404(Absence, pk=pk, teacher=request.user)
    if request.method == 'POST':
        absence.delete()
        messages.success(request, 'Отсъствието е изтрито.')
        return redirect('absence_list')
    return render(request, 'teachers/confirm_delete.html', {'obj': absence, 'type': 'отсъствие'})


# ── Учебни материали ──────────────────────────────────────────

@role_required('teacher')
def material_list(request):
    materials = Material.objects.filter(teacher=request.user).select_related(
        'subject', 'school_class'
    ).order_by('subject__name', 'school_class__name', '-uploaded_at')
    material_groups = [
        {'subject': subject, 'materials': list(group)}
        for subject, group in groupby(materials, key=lambda m: m.subject)
    ]
    return render(request, 'teachers/material_list.html', {'material_groups': material_groups})


@role_required('teacher')
def material_upload(request):
    assignments = _teacher_assignments(request.user)
    classes = list({a.school_class for a in assignments})
    subjects = list({a.subject for a in assignments})

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        subject_id = request.POST.get('subject')
        class_id = request.POST.get('school_class')
        description = request.POST.get('description', '')
        uploaded_file = request.FILES.get('file')

        if not uploaded_file:
            messages.error(request, 'Моля, изберете файл.')
        else:
            Material.objects.create(
                title=title, file=uploaded_file,
                subject_id=subject_id, school_class_id=class_id,
                teacher=request.user, description=description,
            )
            messages.success(request, 'Материалът е качен успешно.')
            return redirect('teacher_material_list')

    return render(request, 'teachers/material_form.html', {
        'classes': classes, 'subjects': subjects,
    })


@role_required('teacher')
def material_edit(request, pk):
    material = get_object_or_404(Material, pk=pk, teacher=request.user)
    assignments = _teacher_assignments(request.user)
    classes = list({a.school_class for a in assignments})
    subjects = list({a.subject for a in assignments})

    if request.method == 'POST':
        material.title = request.POST.get('title', '').strip()
        material.subject_id = request.POST.get('subject')
        material.school_class_id = request.POST.get('school_class')
        material.description = request.POST.get('description', '')
        material.save()
        messages.success(request, 'Материалът е актуализиран.')
        return redirect('teacher_material_list')

    return render(request, 'teachers/material_edit_form.html', {
        'material': material,
        'classes': classes,
        'subjects': subjects,
    })


@role_required('teacher')
def material_delete(request, pk):
    material = get_object_or_404(Material, pk=pk, teacher=request.user)
    if request.method == 'POST':
        material.file.delete(save=False)
        material.delete()
        messages.success(request, 'Материалът е изтрит.')
        return redirect('teacher_material_list')
    return render(request, 'teachers/confirm_delete.html', {'obj': material, 'type': 'материал'})


# ── Статистики ────────────────────────────────────────────────

@role_required('teacher')
def statistics(request):
    import json
    from grades.utils import resolve_period
    period, gtypes = resolve_period(request)
    assignments = _teacher_assignments(request.user)
    stats = []
    for a in assignments:
        students = StudentProfile.objects.filter(school_class=a.school_class)
        avg = Grade.objects.filter(
            subject=a.subject, student__school_class=a.school_class,
            grade_type__in=gtypes,
        ).aggregate(avg=Avg('value'))['avg']
        stats.append({
            'class': a.school_class,
            'subject': a.subject,
            'student_count': students.count(),
            'average': round(avg, 2) if avg else None,
        })

    chart_data = json.dumps({
        'labels': [f"{s['subject']} ({s['class']})" for s in stats],
        'averages': [float(s['average']) if s['average'] else None for s in stats],
    })

    return render(request, 'teachers/statistics.html', {
        'stats': stats,
        'chart_data': chart_data,
        'period': period,
    })


# ── Класен ръководител ───────────────────────────────────────

@role_required('teacher')
def homeroom_overview(request):
    """Обзор на СВОЯ клас за класния ръководител: всички оценки и
    отсъствия на учениците, вкл. по предмети, които той не преподава."""
    from grades.utils import group_grades_by_subject, resolve_period

    school_class = _homeroom_class(request.user)
    if not school_class:
        return render(request, 'teachers/homeroom.html', {'school_class': None})

    period, gtypes = resolve_period(request)
    students = StudentProfile.objects.filter(
        school_class=school_class
    ).select_related('user').order_by('user__first_name', 'user__last_name')

    rows = []
    class_grade_sum = class_grade_count = 0
    total_unexcused = total_excused = 0

    for student in students:
        grades = list(Grade.objects.filter(
            student=student
        ).select_related('subject', 'teacher'))
        # Средният успех се смята само за избрания вид оценки; детайлната
        # таблица по-долу винаги показва всички видове.
        values = [g.value for g in grades if g.grade_type in gtypes]
        average = round(sum(values) / len(values), 2) if values else None

        absences = list(Absence.objects.filter(
            student=student
        ).select_related('subject', 'teacher').order_by('-date'))
        unexcused = sum(1 for a in absences if a.absence_type == 'unexcused')
        excused = len(absences) - unexcused

        rows.append({
            'student': student,
            'average': average,
            'sections': group_grades_by_subject(grades),
            'absences': absences,
            'unexcused': unexcused,
            'excused': excused,
            'total_absences': len(absences),
        })

        class_grade_sum += sum(values)
        class_grade_count += len(values)
        total_unexcused += unexcused
        total_excused += excused

    class_average = round(class_grade_sum / class_grade_count, 2) if class_grade_count else None

    return render(request, 'teachers/homeroom.html', {
        'school_class': school_class,
        'rows': rows,
        'student_count': students.count(),
        'class_average': class_average,
        'total_unexcused': total_unexcused,
        'total_excused': total_excused,
        'total_absences': total_unexcused + total_excused,
        'period': period,
    })


def _absence_counts(student, school_class):
    """Брой извинени/неизвинени за ученика и за целия клас — за обновяване
    на таблицата и картите след промяна на вида на отсъствие."""
    student_total = Absence.objects.filter(student=student).count()
    student_unexcused = Absence.objects.filter(
        student=student, absence_type='unexcused'
    ).count()
    class_total = Absence.objects.filter(student__school_class=school_class).count()
    class_unexcused = Absence.objects.filter(
        student__school_class=school_class, absence_type='unexcused'
    ).count()
    return {
        'student_unexcused': student_unexcused,
        'student_excused': student_total - student_unexcused,
        'student_total': student_total,
        'class_unexcused': class_unexcused,
        'class_excused': class_total - class_unexcused,
        'class_total': class_total,
    }


@role_required('teacher')
def homeroom_absence_excuse(request, pk):
    """Класният ръководител извинява (или връща като неизвинено) отсъствие
    на ученик от своя клас — независимо кой учител го е записал."""
    school_class = _homeroom_class(request.user)
    if not school_class:
        messages.error(request, 'Вие не сте класен ръководител на клас.')
        return redirect('dashboard')

    absence = get_object_or_404(
        Absence, pk=pk, student__school_class=school_class
    )
    # При заявка от страницата (fetch) връщаме JSON, за да обновим реда на
    # място — без презареждане, без връщане в началото на страницата.
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.method == 'POST':
        new_type = request.POST.get('absence_type')
        if new_type in dict(Absence.ABSENCE_TYPE_CHOICES):
            absence.absence_type = new_type
            absence.save(update_fields=['absence_type'])
            text = ('Отсъствието е извинено.' if new_type == 'excused'
                    else 'Отсъствието е върнато като неизвинено.')
            if is_ajax:
                return JsonResponse({
                    'ok': True,
                    'absence_type': new_type,
                    'message': text,
                    **_absence_counts(absence.student, school_class),
                })
            messages.success(request, text)
        else:
            if is_ajax:
                return JsonResponse(
                    {'ok': False, 'message': 'Невалиден вид отсъствие.'}, status=400
                )
            messages.error(request, 'Невалиден вид отсъствие.')

    if is_ajax:
        return JsonResponse({'ok': False, 'message': 'Невалидна заявка.'}, status=400)

    period = request.POST.get('period')
    url = reverse('homeroom_overview')
    if period:
        url = f'{url}?period={period}'
    return redirect(url)


# ── Моят профил ──────────────────────────────────────────────

@role_required('teacher')
def my_profile(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        request.user.email = email
        request.user.save()
        messages.success(request, 'Профилът е актуализиран.')
        return redirect('teacher_profile')
    return render(request, 'teachers/my_profile.html')


# ── Контакти на родители ─────────────────────────────────────

@role_required('teacher', 'admin')
def parent_contacts(request):
    from students.models import ParentProfile
    from school.models import Class
    assignments = _teacher_assignments(request.user)
    available_classes = Class.objects.filter(
        pk__in=assignments.values_list('school_class_id', flat=True)
    ).order_by('name')

    selected_class_id = request.GET.get('class')
    if selected_class_id:
        classes_to_show = available_classes.filter(pk=selected_class_id)
    else:
        classes_to_show = available_classes

    classes_with_parents = []
    for school_class in classes_to_show:
        student_ids = StudentProfile.objects.filter(
            school_class=school_class
        ).values_list('pk', flat=True)
        parents = ParentProfile.objects.filter(
            children__pk__in=student_ids
        ).select_related('user').prefetch_related('children__user').distinct()
        classes_with_parents.append({'school_class': school_class, 'parents': parents})

    return render(request, 'teachers/parent_contacts.html', {
        'classes_with_parents': classes_with_parents,
        'available_classes': available_classes,
        'selected_class_id': selected_class_id,
    })


@role_required('teacher', 'admin')
def student_contacts(request):
    from school.models import Class
    assignments = _teacher_assignments(request.user)
    available_classes = Class.objects.filter(
        pk__in=assignments.values_list('school_class_id', flat=True)
    ).order_by('name')

    selected_class_id = request.GET.get('class')
    if selected_class_id:
        classes_to_show = available_classes.filter(pk=selected_class_id)
    else:
        classes_to_show = available_classes

    classes_with_students = []
    for school_class in classes_to_show:
        students = StudentProfile.objects.filter(
            school_class=school_class
        ).select_related('user').prefetch_related('parents__user').order_by('user__first_name', 'user__last_name')
        classes_with_students.append({'school_class': school_class, 'students': students})

    return render(request, 'teachers/student_contacts.html', {
        'classes_with_students': classes_with_students,
        'available_classes': available_classes,
        'selected_class_id': selected_class_id,
    })


# ── Учебно разписание ─────────────────────────────────────────

@role_required('teacher')
def schedule(request):
    """Собственото седмично разписание на учителя — класове, зали и
    заместванията за деня."""
    from timetable import services
    from timetable.models import SchoolYear

    year = SchoolYear.current()
    today = date.today()
    rows = services.teacher_week_grid(year, request.user) if year else []
    today_rows = services.lessons_on_date(year, today, teacher=request.user) if year else []

    return render(request, 'teachers/schedule.html', {
        'year': year, 'rows': rows, 'today': today, 'today_rows': today_rows,
        'days': [(day, services.DAY_NAMES[day]) for day in services.DAYS],
        'lesson_count': sum(1 for row in rows for cell in row['cells'] if cell['lesson']),
    })


@role_required('teacher')
def lesson_topics(request):
    """Тема на урока за конкретна календарна дата — само за часовете, по които
    учителят е основен преподавател или назначен заместник."""
    import datetime
    from timetable import services
    from timetable.models import LessonTopic, SchoolYear

    year = SchoolYear.current()
    raw_date = request.GET.get('date') or request.POST.get('date')
    try:
        day = datetime.date.fromisoformat(raw_date) if raw_date else date.today()
    except ValueError:
        day = date.today()

    if request.method == 'POST':
        from school.models import Class
        from timetable.models import Period

        school_class = get_object_or_404(Class, pk=request.POST.get('school_class'))
        period = get_object_or_404(Period, pk=request.POST.get('period'))
        topic_text = request.POST.get('topic', '').strip()

        lesson = services.can_teach_on_date(request.user, school_class, period, day)
        if lesson is None:
            messages.error(request, 'Можете да въвеждате тема само за свои часове за тази дата.')
        elif not topic_text:
            LessonTopic.objects.filter(
                date=day, school_class=school_class, period=period).delete()
            messages.success(request, 'Темата е премахната.')
        else:
            LessonTopic.objects.update_or_create(
                date=day, school_class=school_class, period=period,
                defaults={'subject': lesson.subject, 'teacher': request.user,
                          'topic': topic_text,
                          'note': request.POST.get('note', '').strip()},
            )
            messages.success(request, 'Темата на урока е записана.')
        return redirect(f"{request.path}?date={day.isoformat()}")

    rows = []
    if year:
        topics = {
            (topic.school_class_id, topic.period_id): topic
            for topic in LessonTopic.objects.filter(date=day)
        }
        for row in services.lessons_on_date(year, day, teacher=request.user):
            if row['is_cancelled'] or row['teacher'] != request.user:
                continue
            row['topic'] = topics.get(
                (row['lesson'].version.school_class_id, row['lesson'].period_id))
            row['is_substitute'] = row['lesson'].teacher_id != request.user.pk
            rows.append(row)

    return render(request, 'teachers/lesson_topics.html', {
        'date': day, 'rows': rows, 'today': date.today(),
        'is_weekend': day.isoweekday() not in services.DAYS,
    })


@role_required('teacher')
def my_absences(request):
    """Учителят регистрира собствено отсъствие — то се потвърждава от администратор."""
    import datetime
    from timetable.models import TeacherAbsence

    if request.method == 'POST':
        try:
            start = datetime.date.fromisoformat(request.POST.get('start_date'))
            end = datetime.date.fromisoformat(request.POST.get('end_date'))
        except (TypeError, ValueError):
            messages.error(request, 'Въведете валидни дати.')
            return redirect('teacher_my_absences')

        if end < start:
            messages.error(request, 'Крайната дата не може да е преди началната.')
        else:
            TeacherAbsence.objects.create(
                teacher=request.user, start_date=start, end_date=end,
                reason=request.POST.get('reason', '').strip(),
                status=TeacherAbsence.PENDING, created_by=request.user,
            )
            messages.success(
                request, 'Отсъствието е заявено и очаква потвърждение от администратор.')
        return redirect('teacher_my_absences')

    return render(request, 'teachers/my_absences.html', {
        'absences': TeacherAbsence.objects.filter(teacher=request.user),
        'today': date.today(),
    })


@role_required('teacher')
def my_substitutions(request):
    """Заместванията, възложени на учителя."""
    from timetable.models import Substitution

    substitutions = Substitution.objects.filter(
        substitute_teacher=request.user, is_cancelled=False,
    ).select_related('school_class', 'period', 'subject', 'original_teacher', 'room')

    today = date.today()
    return render(request, 'teachers/substitutions.html', {
        'upcoming': [s for s in substitutions if s.date >= today],
        'past': [s for s in substitutions if s.date < today],
        'today': today,
    })


# ── AJAX: ученици по клас ─────────────────────────────────────

from django.http import JsonResponse

def students_by_class(request):
    class_id = request.GET.get('class_id')
    students = StudentProfile.objects.filter(
        school_class_id=class_id
    ).select_related('user').order_by('user__first_name', 'user__last_name')
    data = [{'id': s.pk, 'name': s.user.get_full_name()} for s in students]
    return JsonResponse(data, safe=False)


@role_required('teacher')
def class_subjects_by_date(request):
    """Класовете и предметите, за които учителят може да въвежда отсъствия на
    подадената дата — постоянните му назначения плюс заместванията за деня."""
    import datetime

    raw_date = request.GET.get('date')
    try:
        day = datetime.date.fromisoformat(raw_date) if raw_date else date.today()
    except ValueError:
        day = date.today()

    options = _teacher_class_subject_options(request.user, day)
    classes = sorted({c for c, s in options.values()}, key=lambda c: c.name)
    data = {
        'classes': [{'id': c.pk, 'name': c.name} for c in classes],
        'pairs': [
            {'class_id': cid, 'subject_id': sid, 'subject_name': s.name}
            for (cid, sid), (c, s) in options.items()
        ],
    }
    return JsonResponse(data)
