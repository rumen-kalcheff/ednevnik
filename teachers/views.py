from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Avg
from collections import Counter
from itertools import groupby
from datetime import date
from accounts.decorators import role_required
from school.models import TeacherClassSubject, Timetable
from students.models import StudentProfile
from grades.models import Grade, Absence
from materials.models import Material


def _teacher_assignments(user):
    return TeacherClassSubject.objects.filter(teacher=user).select_related('school_class', 'subject')


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
            current_counts = Counter(
                Grade.objects.filter(
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
    grades_by_student = {}
    if valid:
        existing = Grade.objects.filter(
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
    assignments = _teacher_assignments(request.user)
    classes = list({a.school_class for a in assignments})
    subjects = list({a.subject for a in assignments})

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

        if absence_date_obj > date.today():
            messages.error(request, 'Датата не може да бъде в бъдещето.')
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

    return render(request, 'teachers/absence_form.html', {
        'classes': classes, 'subjects': subjects,
        'absence_types': Absence.ABSENCE_TYPE_CHOICES,
        'today': date.today(),
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


# ── Разписание ────────────────────────────────────────────────

@role_required('teacher')
def schedule(request):
    entries = Timetable.objects.filter(
        assignment__teacher=request.user
    ).select_related('assignment__school_class', 'assignment__subject')

    days = [1, 2, 3, 4, 5]
    hours = list(range(1, 9))
    grid = {day: {hour: None for hour in hours} for day in days}
    for entry in entries:
        grid[entry.day_of_week][entry.hour_number] = entry

    day_names = dict(Timetable.DAY_CHOICES)
    return render(request, 'teachers/schedule.html', {
        'grid': grid, 'days': days, 'hours': hours, 'day_names': day_names,
    })


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
        ).select_related('user').order_by('user__last_name')
        classes_with_students.append({'school_class': school_class, 'students': students})

    return render(request, 'teachers/student_contacts.html', {
        'classes_with_students': classes_with_students,
        'available_classes': available_classes,
        'selected_class_id': selected_class_id,
    })


# ── AJAX: ученици по клас ─────────────────────────────────────

from django.http import JsonResponse

def students_by_class(request):
    class_id = request.GET.get('class_id')
    students = StudentProfile.objects.filter(
        school_class_id=class_id
    ).select_related('user').order_by('user__last_name')
    data = [{'id': s.pk, 'name': s.user.get_full_name()} for s in students]
    return JsonResponse(data, safe=False)
