from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from accounts.models import User
from accounts.decorators import role_required
from school.models import Class, Subject, TeacherClassSubject, ROOM_TYPE_CHOICES
from students.models import StudentProfile, ParentProfile
from teachers.models import TeacherProfile
from timetable.models import Lesson


def _used_in_timetable(**filters):
    """Дали обектът участва в разписание (чернова или публикувано)."""
    return Lesson.objects.filter(**filters).exists()


# ── Потребители ──────────────────────────────────────────────

@role_required('admin')
def user_list(request):
    selected_role = request.GET.get('role', '')
    selected_class_id = request.GET.get('class', '')

    base_qs = User.objects.exclude(is_superuser=True)
    role_counts = {value: base_qs.filter(role=value).count() for value, _ in User.ROLE_CHOICES}

    users = None
    classes = None
    student_groups = None

    if selected_role == 'student':
        classes = Class.objects.all().order_by('name')
        classes_to_show = classes.filter(pk=selected_class_id) if selected_class_id else classes

        student_groups = []
        for school_class in classes_to_show:
            class_users = base_qs.filter(
                role='student', student_profile__school_class=school_class
            ).order_by('last_name', 'first_name')
            student_groups.append({'school_class': school_class, 'users': class_users})

        if not selected_class_id:
            unassigned = base_qs.filter(
                role='student', student_profile__school_class__isnull=True
            ).order_by('last_name', 'first_name')
            if unassigned.exists():
                student_groups.append({'school_class': None, 'users': unassigned})
    else:
        users = base_qs.select_related('student_profile__school_class')
        if selected_role:
            users = users.filter(role=selected_role)
        users = users.order_by('role', 'last_name', 'first_name')

    return render(request, 'adminpanel/user_list.html', {
        'users': users,
        'student_groups': student_groups,
        'classes': classes,
        'role_counts': role_counts,
        'total_count': sum(role_counts.values()),
        'selected_role': selected_role,
        'selected_class_id': selected_class_id,
    })


@role_required('admin')
def user_create(request):
    classes = Class.objects.all()
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        role = request.POST.get('role')
        password = request.POST.get('password', '').strip()

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Потребителското име вече съществува.')
            return render(request, 'adminpanel/user_form.html', {'action': 'Създай', 'classes': classes})

        email = request.POST.get('email', '').strip()
        user = User.objects.create_user(
            username=username, password=password,
            first_name=first_name, last_name=last_name, role=role, email=email,
        )
        profile = _create_profile(user)
        if role == 'student' and profile:
            class_id = request.POST.get('school_class') or None
            profile.school_class_id = class_id
            profile.egn = request.POST.get('egn', '').strip()
            profile.save()
        if role == 'parent' and profile:
            profile.phone = request.POST.get('phone', '').strip()
            profile.save()
        messages.success(request, f'Потребителят {user.get_full_name()} е създаден.')
        return redirect('user_list')

    return render(request, 'adminpanel/user_form.html', {'action': 'Създай', 'classes': classes})


@role_required('admin')
def user_edit(request, pk):
    user = get_object_or_404(User, pk=pk)
    classes = Class.objects.all()
    student_profile = getattr(user, 'student_profile', None)
    parent_profile = getattr(user, 'parent_profile', None)
    if request.method == 'POST':
        user.first_name = request.POST.get('first_name', '').strip()
        user.last_name = request.POST.get('last_name', '').strip()
        user.email = request.POST.get('email', '').strip()
        user.role = request.POST.get('role')
        new_password = request.POST.get('password', '').strip()
        if new_password:
            user.set_password(new_password)
        user.save()
        if user.role == 'student':
            profile, _ = StudentProfile.objects.get_or_create(user=user)
            profile.school_class_id = request.POST.get('school_class') or None
            profile.egn = request.POST.get('egn', '').strip()
            profile.save()
        if user.role == 'parent':
            profile, _ = ParentProfile.objects.get_or_create(user=user)
            profile.phone = request.POST.get('phone', '').strip()
            profile.save()
        messages.success(request, 'Потребителят е актуализиран.')
        return redirect('user_list')

    return render(request, 'adminpanel/user_form.html', {
        'action': 'Редактирай', 'obj': user,
        'classes': classes, 'student_profile': student_profile,
        'parent_profile': parent_profile,
    })


@role_required('admin')
def user_delete(request, pk):
    """Преподавател, който участва в разписание, не се изтрива, а се деактивира."""
    user = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        name = user.get_full_name()
        if user.role == 'teacher' and _used_in_timetable(teacher=user):
            user.is_active = False
            user.save(update_fields=['is_active'])
            messages.warning(
                request, f'{name} участва в разписание — вместо изтриване е деактивиран(а).')
        else:
            user.delete()
            messages.success(request, f'Потребителят {name} е изтрит.')
        return redirect('user_list')
    return render(request, 'adminpanel/confirm_delete.html', {'obj': user, 'type': 'потребител'})


# ── Класове ──────────────────────────────────────────────────

@role_required('admin')
def class_list(request):
    classes = Class.objects.select_related('homeroom_teacher').all()
    return render(request, 'adminpanel/class_list.html', {'classes': classes})


@role_required('admin')
def class_create(request):
    teachers = User.objects.filter(role='teacher').order_by('last_name')
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        teacher_id = request.POST.get('homeroom_teacher') or None
        if Class.objects.filter(name=name).exists():
            messages.error(request, 'Класът вече съществува.')
        elif teacher_id and Class.objects.filter(homeroom_teacher_id=teacher_id).exists():
            messages.error(request, 'Този учител вече е класен ръководител на друг клас.')
        else:
            Class.objects.create(name=name, homeroom_teacher_id=teacher_id)
            messages.success(request, f'Класът {name} е създаден.')
            return redirect('class_list')
    return render(request, 'adminpanel/class_form.html', {'action': 'Създай', 'teachers': teachers})


@role_required('admin')
def class_edit(request, pk):
    school_class = get_object_or_404(Class, pk=pk)
    teachers = User.objects.filter(role='teacher').order_by('last_name')
    if request.method == 'POST':
        new_teacher_id = request.POST.get('homeroom_teacher') or None
        if new_teacher_id and str(new_teacher_id) != str(school_class.homeroom_teacher_id):
            if Class.objects.filter(homeroom_teacher_id=new_teacher_id).exists():
                messages.error(request, 'Този учител вече е класен ръководител на друг клас.')
                return render(request, 'adminpanel/class_form.html', {
                    'action': 'Редактирай', 'obj': school_class, 'teachers': teachers
                })
        school_class.name = request.POST.get('name', '').strip()
        school_class.homeroom_teacher_id = new_teacher_id
        school_class.save()
        messages.success(request, 'Класът е актуализиран.')
        return redirect('class_list')
    return render(request, 'adminpanel/class_form.html', {
        'action': 'Редактирай', 'obj': school_class, 'teachers': teachers
    })


@role_required('admin')
def class_delete(request, pk):
    """Клас, който участва в разписание, не се изтрива, а се деактивира."""
    school_class = get_object_or_404(Class, pk=pk)
    if request.method == 'POST':
        if _used_in_timetable(version__school_class=school_class):
            school_class.is_active = False
            school_class.save(update_fields=['is_active'])
            messages.warning(
                request,
                f'Клас {school_class} участва в разписание — вместо изтриване е деактивиран.')
        else:
            school_class.delete()
            messages.success(request, 'Класът е изтрит.')
        return redirect('class_list')
    return render(request, 'adminpanel/confirm_delete.html', {'obj': school_class, 'type': 'клас'})


# ── Предмети ─────────────────────────────────────────────────

@role_required('admin')
def subject_list(request):
    subjects = Subject.objects.all()
    return render(request, 'adminpanel/subject_list.html', {'subjects': subjects})


@role_required('admin')
def subject_create(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if Subject.objects.filter(name=name).exists():
            messages.error(request, 'Предметът вече съществува.')
        else:
            Subject.objects.create(
                name=name,
                required_room_type=request.POST.get('required_room_type', ''),
                is_foreign_language=bool(request.POST.get('is_foreign_language')),
                is_active=bool(request.POST.get('is_active')),
            )
            messages.success(request, f'Предметът {name} е създаден.')
            return redirect('subject_list')
    return render(request, 'adminpanel/subject_form.html', {
        'action': 'Създай', 'room_types': ROOM_TYPE_CHOICES,
    })


@role_required('admin')
def subject_edit(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    if request.method == 'POST':
        subject.name = request.POST.get('name', '').strip()
        subject.required_room_type = request.POST.get('required_room_type', '')
        subject.is_foreign_language = bool(request.POST.get('is_foreign_language'))
        subject.is_active = bool(request.POST.get('is_active'))
        subject.save()
        messages.success(request, 'Предметът е актуализиран.')
        return redirect('subject_list')
    return render(request, 'adminpanel/subject_form.html', {
        'action': 'Редактирай', 'obj': subject, 'room_types': ROOM_TYPE_CHOICES,
    })


@role_required('admin')
def subject_delete(request, pk):
    """Предмет, който участва в разписание, не се изтрива, а се деактивира."""
    subject = get_object_or_404(Subject, pk=pk)
    if request.method == 'POST':
        if _used_in_timetable(subject=subject):
            subject.is_active = False
            subject.save(update_fields=['is_active'])
            messages.warning(
                request, f'{subject} участва в разписание — вместо изтриване е деактивиран.')
        else:
            subject.delete()
            messages.success(request, 'Предметът е изтрит.')
        return redirect('subject_list')
    return render(request, 'adminpanel/confirm_delete.html', {'obj': subject, 'type': 'предмет'})


# ── Назначения учител → клас + предмет ───────────────────────

@role_required('admin')
def assignment_list(request):
    assignments = TeacherClassSubject.objects.select_related('teacher', 'school_class', 'subject').all()
    return render(request, 'adminpanel/assignment_list.html', {'assignments': assignments})


@role_required('admin')
def assignment_create(request):
    teachers = User.objects.filter(role='teacher').order_by('last_name')
    classes = Class.objects.all()
    subjects = Subject.objects.all()
    if request.method == 'POST':
        teacher_id = request.POST.get('teacher')
        class_id = request.POST.get('school_class')
        subject_id = request.POST.get('subject')
        if TeacherClassSubject.objects.filter(teacher_id=teacher_id, school_class_id=class_id, subject_id=subject_id).exists():
            messages.error(request, 'Това назначение вече съществува.')
        else:
            TeacherClassSubject.objects.create(teacher_id=teacher_id, school_class_id=class_id, subject_id=subject_id)
            messages.success(request, 'Назначението е създадено.')
            return redirect('assignment_list')
    return render(request, 'adminpanel/assignment_form.html', {
        'teachers': teachers, 'classes': classes, 'subjects': subjects
    })


@role_required('admin')
def assignment_delete(request, pk):
    assignment = get_object_or_404(TeacherClassSubject, pk=pk)
    if request.method == 'POST':
        assignment.delete()
        messages.success(request, 'Назначението е изтрито.')
        return redirect('assignment_list')
    return render(request, 'adminpanel/confirm_delete.html', {'obj': assignment, 'type': 'назначение'})


# ── Свързване родител ↔ ученик ────────────────────────────────

@role_required('admin')
def parent_link(request):
    parents = ParentProfile.objects.select_related('user').prefetch_related('children__user').all()
    students = StudentProfile.objects.select_related('user', 'school_class').all()
    if request.method == 'POST':
        parent_id = request.POST.get('parent')
        student_ids = request.POST.getlist('students')
        parent = get_object_or_404(ParentProfile, pk=parent_id)
        parent.children.set(student_ids)
        messages.success(request, 'Връзките са актуализирани.')
        return redirect('parent_link')
    return render(request, 'adminpanel/parent_link.html', {'parents': parents, 'students': students})


# ── Административни справки ───────────────────────────────────

@role_required('admin')
def admin_statistics(request):
    import json
    from django.db.models import Avg, Count
    from grades.models import Grade, Absence
    from grades.utils import resolve_period
    from students.models import StudentProfile

    period, gtypes = resolve_period(request)
    total_students = StudentProfile.objects.count()
    total_teachers = User.objects.filter(role='teacher').count()
    total_parents = User.objects.filter(role='parent').count()
    total_classes = Class.objects.count()
    total_subjects = Subject.objects.count()
    total_grades = Grade.objects.count()
    total_absences = Absence.objects.count()
    excused = Absence.objects.filter(absence_type='excused').count()
    unexcused = Absence.objects.filter(absence_type='unexcused').count()
    overall_avg = Grade.objects.filter(grade_type__in=gtypes).aggregate(avg=Avg('value'))['avg']

    classes = Class.objects.prefetch_related('students').all()
    class_stats = []
    for c in classes:
        students = StudentProfile.objects.filter(school_class=c)
        avg = Grade.objects.filter(
            student__school_class=c, grade_type__in=gtypes
        ).aggregate(avg=Avg('value'))['avg']
        abs_count = Absence.objects.filter(student__school_class=c).count()
        class_stats.append({
            'class': c,
            'student_count': students.count(),
            'average': round(avg, 2) if avg else None,
            'absence_count': abs_count,
        })

    chart_data = json.dumps({
        'labels': [s['class'].name for s in class_stats],
        'averages': [float(s['average']) if s['average'] else None for s in class_stats],
        'absences': [s['absence_count'] for s in class_stats],
    })

    return render(request, 'adminpanel/statistics.html', {
        'total_students': total_students,
        'total_teachers': total_teachers,
        'total_parents': total_parents,
        'total_classes': total_classes,
        'total_subjects': total_subjects,
        'total_grades': total_grades,
        'total_absences': total_absences,
        'excused': excused,
        'unexcused': unexcused,
        'overall_avg': round(overall_avg, 2) if overall_avg else None,
        'class_stats': class_stats,
        'chart_data': chart_data,
        'period': period,
    })


# ── Контакти на родители ─────────────────────────────────────

@role_required('admin')
def parent_contacts(request):
    from school.models import Class
    available_classes = Class.objects.all().order_by('name')
    selected_class_id = request.GET.get('class')
    classes_to_show = available_classes.filter(pk=selected_class_id) if selected_class_id else available_classes

    classes_with_parents = []
    for school_class in classes_to_show:
        student_ids = StudentProfile.objects.filter(
            school_class=school_class
        ).values_list('pk', flat=True)
        parents = ParentProfile.objects.filter(
            children__pk__in=student_ids
        ).select_related('user').prefetch_related('children__user').distinct()
        classes_with_parents.append({'school_class': school_class, 'parents': parents})

    return render(request, 'adminpanel/parent_contacts.html', {
        'classes_with_parents': classes_with_parents,
        'available_classes': available_classes,
        'selected_class_id': selected_class_id,
    })


@role_required('admin')
def student_contacts(request):
    from school.models import Class
    available_classes = Class.objects.all().order_by('name')
    selected_class_id = request.GET.get('class')
    classes_to_show = available_classes.filter(pk=selected_class_id) if selected_class_id else available_classes

    classes_with_students = []
    for school_class in classes_to_show:
        students = StudentProfile.objects.filter(
            school_class=school_class
        ).select_related('user').prefetch_related('parents__user').order_by('user__first_name', 'user__last_name')
        classes_with_students.append({'school_class': school_class, 'students': students})

    return render(request, 'adminpanel/student_contacts.html', {
        'classes_with_students': classes_with_students,
        'available_classes': available_classes,
        'selected_class_id': selected_class_id,
    })


# ── Помощна функция ───────────────────────────────────────────

def _create_profile(user):
    if user.role == 'teacher':
        profile, _ = TeacherProfile.objects.get_or_create(user=user)
        return profile
    elif user.role == 'student':
        profile, _ = StudentProfile.objects.get_or_create(user=user)
        return profile
    elif user.role == 'parent':
        profile, _ = ParentProfile.objects.get_or_create(user=user)
        return profile
