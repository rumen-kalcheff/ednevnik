from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Avg
from itertools import groupby
from accounts.decorators import role_required
from school.models import Timetable
from grades.models import Grade, Absence
from materials.models import Material
from students.models import StudentProfile


def _get_child(request, parent_profile):
    children = parent_profile.children.select_related('user', 'school_class')
    if not children.exists():
        return None, children
    child_id = request.GET.get('child')
    if child_id:
        child = get_object_or_404(children, pk=child_id)
    else:
        child = children.first()
    return child, children


@role_required('parent')
def grade_list(request):
    parent = request.user.parent_profile
    child, children = _get_child(request, parent)

    sections = []
    subjects = []
    selected_subject = request.GET.get('subject')

    if child:
        grades = Grade.objects.filter(student=child).select_related('subject', 'teacher')
        if selected_subject:
            grades = grades.filter(subject_id=selected_subject)
        from school.models import Subject
        from grades.utils import group_grades_by_subject
        subject_ids = child.grades.values_list('subject', flat=True).distinct()
        subjects = Subject.objects.filter(pk__in=subject_ids)
        sections = group_grades_by_subject(grades)

    return render(request, 'parents/grade_list.html', {
        'sections': sections, 'child': child, 'children': children,
        'subjects': subjects, 'selected_subject': selected_subject,
    })


@role_required('parent')
def absence_list(request):
    parent = request.user.parent_profile
    child, children = _get_child(request, parent)

    absences = Absence.objects.none()
    excused = unexcused = 0

    if child:
        absences = Absence.objects.filter(student=child).select_related('subject', 'teacher')
        excused = absences.filter(absence_type='excused').count()
        unexcused = absences.filter(absence_type='unexcused').count()

    return render(request, 'parents/absence_list.html', {
        'absences': absences, 'child': child, 'children': children,
        'excused': excused, 'unexcused': unexcused, 'total': excused + unexcused,
    })


@role_required('parent')
def schedule(request):
    parent = request.user.parent_profile
    child, children = _get_child(request, parent)

    grid = {}
    days = [1, 2, 3, 4, 5]
    hours = list(range(1, 9))
    day_names = dict(Timetable.DAY_CHOICES)

    if child and child.school_class:
        entries = Timetable.objects.filter(
            assignment__school_class=child.school_class
        ).select_related('assignment__subject', 'assignment__teacher')
        grid = {day: {hour: None for hour in hours} for day in days}
        for entry in entries:
            grid[entry.day_of_week][entry.hour_number] = entry

    return render(request, 'parents/schedule.html', {
        'grid': grid, 'days': days, 'hours': hours, 'day_names': day_names,
        'child': child, 'children': children,
    })


@role_required('parent')
def material_list(request):
    parent = request.user.parent_profile
    child, children = _get_child(request, parent)

    materials = Material.objects.none()
    material_groups = []
    subjects = []
    selected_subject = request.GET.get('subject')

    if child and child.school_class:
        materials = Material.objects.filter(
            school_class=child.school_class
        ).select_related('subject', 'teacher').order_by('subject__name', '-uploaded_at')
        if selected_subject:
            materials = materials.filter(subject_id=selected_subject)
        from school.models import Subject
        subjects = Subject.objects.filter(
            materials__school_class=child.school_class
        ).distinct()
        material_groups = [
            {'subject': subject, 'materials': list(group)}
            for subject, group in groupby(materials, key=lambda m: m.subject)
        ]

    return render(request, 'parents/material_list.html', {
        'material_groups': material_groups, 'child': child, 'children': children,
        'subjects': subjects, 'selected_subject': selected_subject,
    })


@role_required('parent')
def my_profile(request):
    parent = request.user.parent_profile
    if request.method == 'POST':
        request.user.email = request.POST.get('email', '').strip()
        request.user.save()
        parent.phone = request.POST.get('phone', '').strip()
        parent.save()
        messages.success(request, 'Профилът е актуализиран.')
        return redirect('parent_profile')
    return render(request, 'parents/my_profile.html', {'parent': parent})


@role_required('parent')
def teacher_contacts(request):
    from school.models import TeacherClassSubject
    parent = request.user.parent_profile
    child, children = _get_child(request, parent)

    assignments = []
    if child and child.school_class:
        assignments = TeacherClassSubject.objects.filter(
            school_class=child.school_class
        ).select_related('teacher', 'subject').order_by('subject__name')

    return render(request, 'parents/teacher_contacts.html', {
        'assignments': assignments,
        'child': child,
        'children': children,
    })


@role_required('parent')
def statistics(request):
    import json
    parent = request.user.parent_profile
    child, children = _get_child(request, parent)

    stats = []
    overall_avg = None

    if child:
        from school.models import Subject
        subjects = Subject.objects.filter(grades__student=child).distinct()
        for subject in subjects:
            subject_grades = Grade.objects.filter(student=child, subject=subject)
            avg = subject_grades.aggregate(avg=Avg('value'))['avg']
            stats.append({
                'subject': subject,
                'grades': subject_grades,
                'average': round(avg, 2) if avg else None,
                'count': subject_grades.count(),
            })
        raw_avg = Grade.objects.filter(student=child).aggregate(avg=Avg('value'))['avg']
        overall_avg = round(raw_avg, 2) if raw_avg else None

    chart_data = json.dumps({
        'labels': [s['subject'].name for s in stats],
        'averages': [float(s['average']) if s['average'] else None for s in stats],
    })

    return render(request, 'parents/statistics.html', {
        'stats': stats, 'overall_avg': overall_avg,
        'child': child, 'children': children,
        'chart_data': chart_data,
    })
