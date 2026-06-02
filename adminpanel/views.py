from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from accounts.models import User
from accounts.decorators import role_required
from school.models import Class, Subject, TeacherClassSubject, Timetable
from students.models import StudentProfile, ParentProfile
from teachers.models import TeacherProfile


# ── Потребители ──────────────────────────────────────────────

@role_required('admin')
def user_list(request):
    users = User.objects.exclude(is_superuser=True).order_by('role', 'last_name')
    return render(request, 'adminpanel/user_list.html', {'users': users})


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

        user = User.objects.create_user(
            username=username, password=password,
            first_name=first_name, last_name=last_name, role=role,
        )
        profile = _create_profile(user)
        if role == 'student' and profile:
            class_id = request.POST.get('school_class') or None
            profile.school_class_id = class_id
            profile.save()
        messages.success(request, f'Потребителят {user.get_full_name()} е създаден.')
        return redirect('user_list')

    return render(request, 'adminpanel/user_form.html', {'action': 'Създай', 'classes': classes})


@role_required('admin')
def user_edit(request, pk):
    user = get_object_or_404(User, pk=pk)
    classes = Class.objects.all()
    student_profile = getattr(user, 'student_profile', None)
    if request.method == 'POST':
        user.first_name = request.POST.get('first_name', '').strip()
        user.last_name = request.POST.get('last_name', '').strip()
        user.role = request.POST.get('role')
        new_password = request.POST.get('password', '').strip()
        if new_password:
            user.set_password(new_password)
        user.save()
        if user.role == 'student':
            profile, _ = StudentProfile.objects.get_or_create(user=user)
            profile.school_class_id = request.POST.get('school_class') or None
            profile.save()
        messages.success(request, 'Потребителят е актуализиран.')
        return redirect('user_list')

    return render(request, 'adminpanel/user_form.html', {
        'action': 'Редактирай', 'obj': user,
        'classes': classes, 'student_profile': student_profile,
    })


@role_required('admin')
def user_delete(request, pk):
    user = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        name = user.get_full_name()
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
        school_class.name = request.POST.get('name', '').strip()
        school_class.homeroom_teacher_id = request.POST.get('homeroom_teacher') or None
        school_class.save()
        messages.success(request, 'Класът е актуализиран.')
        return redirect('class_list')
    return render(request, 'adminpanel/class_form.html', {
        'action': 'Редактирай', 'obj': school_class, 'teachers': teachers
    })


@role_required('admin')
def class_delete(request, pk):
    school_class = get_object_or_404(Class, pk=pk)
    if request.method == 'POST':
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
            Subject.objects.create(name=name)
            messages.success(request, f'Предметът {name} е създаден.')
            return redirect('subject_list')
    return render(request, 'adminpanel/subject_form.html', {'action': 'Създай'})


@role_required('admin')
def subject_edit(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    if request.method == 'POST':
        subject.name = request.POST.get('name', '').strip()
        subject.save()
        messages.success(request, 'Предметът е актуализиран.')
        return redirect('subject_list')
    return render(request, 'adminpanel/subject_form.html', {'action': 'Редактирай', 'obj': subject})


@role_required('admin')
def subject_delete(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    if request.method == 'POST':
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


# ── Разписание ────────────────────────────────────────────────

@role_required('admin')
def timetable_list(request):
    class_id = request.GET.get('class')
    classes = Class.objects.all()
    entries = Timetable.objects.select_related(
        'assignment__school_class', 'assignment__subject', 'assignment__teacher'
    )
    if class_id:
        entries = entries.filter(assignment__school_class_id=class_id)

    days = [1, 2, 3, 4, 5]
    hours = list(range(1, 9))
    day_names = dict(Timetable.DAY_CHOICES)

    grid = {}
    if class_id:
        grid = {day: {hour: None for hour in hours} for day in days}
        for entry in entries:
            grid[entry.day_of_week][entry.hour_number] = entry

    return render(request, 'adminpanel/timetable_list.html', {
        'classes': classes, 'selected_class': class_id,
        'grid': grid, 'days': days, 'hours': hours, 'day_names': day_names,
        'entries': entries,
    })


@role_required('admin')
def timetable_add(request):
    classes = Class.objects.all()
    assignments = TeacherClassSubject.objects.select_related('teacher', 'school_class', 'subject')
    class_id = request.GET.get('class') or request.POST.get('class_filter')

    if request.method == 'POST':
        assignment_id = request.POST.get('assignment')
        day = request.POST.get('day_of_week')
        hour = request.POST.get('hour_number')

        if not assignment_id:
            return redirect(f'/admin-panel/timetable/add/?class={class_id or ""}')

        assignment = get_object_or_404(TeacherClassSubject, pk=assignment_id)
        if Timetable.objects.filter(
            assignment__school_class=assignment.school_class,
            day_of_week=day, hour_number=hour
        ).exists():
            messages.error(request, 'В този час вече има предмет за този клас.')
        else:
            Timetable.objects.create(assignment_id=assignment_id, day_of_week=day, hour_number=hour)
            messages.success(request, 'Часът е добавен в разписанието.')
            return redirect(f'/admin-panel/timetable/?class={assignment.school_class_id}')

    if class_id:
        assignments = assignments.filter(school_class_id=class_id)

    return render(request, 'adminpanel/timetable_form.html', {
        'classes': classes, 'assignments': assignments,
        'days': Timetable.DAY_CHOICES, 'hours': Timetable.HOUR_CHOICES,
        'selected_class': class_id,
    })


@role_required('admin')
def timetable_delete(request, pk):
    entry = get_object_or_404(Timetable, pk=pk)
    class_id = entry.assignment.school_class_id
    if request.method == 'POST':
        entry.delete()
        messages.success(request, 'Часът е премахнат от разписанието.')
        return redirect(f'/admin-panel/timetable/?class={class_id}')
    return render(request, 'adminpanel/confirm_delete.html', {'obj': entry, 'type': 'час от разписанието'})


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
