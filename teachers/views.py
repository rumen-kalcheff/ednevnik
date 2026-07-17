from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Avg
from datetime import date
from accounts.decorators import role_required
from school.models import TeacherClassSubject, Timetable
from students.models import StudentProfile
from grades.models import Grade, Absence
from materials.models import Material


def _teacher_assignments(user):
    return TeacherClassSubject.objects.filter(teacher=user).select_related('school_class', 'subject')


# ── Оценки ───────────────────────────────────────────────────

@role_required('teacher')
def grade_list(request):
    assignments = _teacher_assignments(request.user)
    class_id = request.GET.get('class')
    subject_id = request.GET.get('subject')

    grades = Grade.objects.filter(teacher=request.user).select_related(
        'student__user', 'subject', 'student__school_class'
    )
    if class_id:
        grades = grades.filter(student__school_class_id=class_id)
    if subject_id:
        grades = grades.filter(subject_id=subject_id)

    classes = [a.school_class for a in assignments]
    subjects = [a.subject for a in assignments]

    return render(request, 'teachers/grade_list.html', {
        'grades': grades, 'classes': classes, 'subjects': subjects,
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

    absences = Absence.objects.filter(teacher=request.user).select_related(
        'student__user', 'subject', 'student__school_class'
    )
    if class_id:
        absences = absences.filter(student__school_class_id=class_id)

    classes = [a.school_class for a in assignments]
    return render(request, 'teachers/absence_list.html', {
        'absences': absences, 'classes': classes, 'selected_class': class_id,
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
        absence.date = request.POST.get('date')
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
    materials = Material.objects.filter(teacher=request.user).select_related('subject', 'school_class')
    return render(request, 'teachers/material_list.html', {'materials': materials})


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
    assignments = _teacher_assignments(request.user)
    stats = []
    for a in assignments:
        students = StudentProfile.objects.filter(school_class=a.school_class)
        avg = Grade.objects.filter(
            subject=a.subject, student__school_class=a.school_class
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
