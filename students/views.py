from django.shortcuts import render, get_object_or_404
from django.db.models import Avg
from itertools import groupby
from accounts.decorators import role_required
from grades.models import Grade, Absence
from materials.models import Material
from students.models import StudentProfile


def _get_student_profile(user):
    return get_object_or_404(user.student_profile.__class__, user=user)


@role_required('student')
def grade_list(request):
    profile = request.user.student_profile
    subject_id = request.GET.get('subject')

    grades = Grade.objects.filter(student=profile).select_related('subject', 'teacher')
    if subject_id:
        grades = grades.filter(subject_id=subject_id)

    from school.models import Subject
    from grades.utils import group_grades_by_subject
    subject_ids = profile.grades.values_list('subject', flat=True).distinct()
    subjects = Subject.objects.filter(pk__in=subject_ids)

    return render(request, 'students/grade_list.html', {
        'sections': group_grades_by_subject(grades),
        'subjects': subjects,
        'selected_subject': subject_id,
        'school_class': profile.school_class,
    })


@role_required('student')
def absence_list(request):
    profile = request.user.student_profile
    absences = Absence.objects.filter(student=profile).select_related(
        'subject', 'teacher'
    ).order_by('subject__name', '-date')

    excused = absences.filter(absence_type='excused').count()
    unexcused = absences.filter(absence_type='unexcused').count()

    subject_rows = []
    for subject, group in groupby(absences, key=lambda a: a.subject):
        items = list(group)
        row_unexcused = sum(1 for a in items if a.absence_type == 'unexcused')
        subject_rows.append({
            'subject': subject,
            'absences': items,
            'unexcused': row_unexcused,
            'excused': len(items) - row_unexcused,
            'total': len(items),
        })

    return render(request, 'students/absence_list.html', {
        'subject_rows': subject_rows,
        'excused': excused,
        'unexcused': unexcused,
        'total': excused + unexcused,
    })


@role_required('student')
def material_list(request):
    profile = request.user.student_profile
    subject_id = request.GET.get('subject')

    materials = Material.objects.filter(
        school_class=profile.school_class
    ).select_related('subject', 'teacher').order_by('subject__name', '-uploaded_at')

    if subject_id:
        materials = materials.filter(subject_id=subject_id)

    from school.models import Subject
    subjects = Subject.objects.filter(
        materials__school_class=profile.school_class
    ).distinct()

    material_groups = [
        {'subject': subject, 'materials': list(group)}
        for subject, group in groupby(materials, key=lambda m: m.subject)
    ]

    return render(request, 'students/material_list.html', {
        'material_groups': material_groups,
        'subjects': subjects,
        'selected_subject': subject_id,
    })


@role_required('student')
def class_info(request):
    profile = request.user.student_profile
    school_class = profile.school_class
    # Целият клас, подреден по собствено име (както се водят класните списъци);
    # номерът е позицията в тази подредба.
    students = StudentProfile.objects.filter(
        school_class=school_class
    ).select_related('user').order_by('user__first_name', 'user__last_name')

    return render(request, 'students/class_info.html', {
        'school_class': school_class,
        'students': students,
        'me_id': profile.pk,
    })


@role_required('student')
def teacher_contacts(request):
    from school.models import TeacherClassSubject
    profile = request.user.student_profile
    assignments = TeacherClassSubject.objects.filter(
        school_class=profile.school_class
    ).select_related('teacher', 'subject').order_by('subject__name')
    return render(request, 'students/teacher_contacts.html', {
        'assignments': assignments,
        'school_class': profile.school_class,
    })


@role_required('student')
def statistics(request):
    import json
    from grades.utils import resolve_period
    profile = request.user.student_profile
    from school.models import Subject
    period, gtypes = resolve_period(request)
    subjects = Subject.objects.filter(
        grades__student=profile, grades__grade_type__in=gtypes
    ).distinct()

    stats = []
    for subject in subjects:
        subject_grades = Grade.objects.filter(
            student=profile, subject=subject, grade_type__in=gtypes
        )
        avg = subject_grades.aggregate(avg=Avg('value'))['avg']
        stats.append({
            'subject': subject,
            'grades': subject_grades,
            'average': round(avg, 2) if avg else None,
            'count': subject_grades.count(),
        })

    overall_avg = Grade.objects.filter(
        student=profile, grade_type__in=gtypes
    ).aggregate(avg=Avg('value'))['avg']

    chart_data = json.dumps({
        'labels': [s['subject'].name for s in stats],
        'averages': [float(s['average']) if s['average'] else None for s in stats],
    })

    return render(request, 'students/statistics.html', {
        'stats': stats,
        'overall_avg': round(overall_avg, 2) if overall_avg else None,
        'chart_data': chart_data,
        'period': period,
    })


# ── Учебно разписание ─────────────────────────────────────────

@role_required('student')
def schedule(request):
    """Публикуваното разписание на класа на ученика."""
    from datetime import date, timedelta
    from timetable import services
    from timetable.models import LessonTopic, SchoolYear

    profile = request.user.student_profile
    school_class = profile.school_class
    year = SchoolYear.current()

    rows = []
    setting = None
    today_changes = []
    if year and school_class:
        setting = services.class_setting(year, school_class)
        version = services.published_version(year, school_class)
        rows = services.week_grid(version, services.class_periods(year, school_class))

        monday = date.today() - timedelta(days=date.today().isoweekday() - 1)
        week_dates = {day: monday + timedelta(days=day - 1) for day in services.DAYS}
        topics = {
            (topic.period_id, topic.date.isoweekday()): topic
            for topic in LessonTopic.objects.filter(
                school_class=school_class,
                date__range=(week_dates[services.DAYS[0]], week_dates[services.DAYS[-1]]),
            )
        }
        for row in rows:
            for cell in row['cells']:
                cell['date'] = week_dates[cell['day']]
                cell['topic'] = topics.get((row['period'].pk, cell['day']))

        today_changes = [
            row for row in services.lessons_on_date(
                year, date.today(), school_class=school_class)
            if row['substitution']
        ]

    return render(request, 'students/schedule.html', {
        'school_class': school_class, 'year': year, 'setting': setting,
        'rows': rows, 'today': date.today(), 'today_changes': today_changes,
        'days': [(day, services.DAY_NAMES[day]) for day in services.DAYS],
    })
