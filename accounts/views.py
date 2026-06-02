from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from .decorators import role_required


def home_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'accounts/home.html')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Невалидно потребителско име или парола.')

    return render(request, 'accounts/login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def dashboard_view(request):
    role = request.user.role
    if role == 'admin':
        return redirect('admin_dashboard')
    elif role == 'teacher':
        return redirect('teacher_dashboard')
    elif role == 'student':
        return redirect('student_dashboard')
    elif role == 'parent':
        return redirect('parent_dashboard')
    return redirect('login')


@role_required('admin')
def admin_dashboard(request):
    return render(request, 'dashboards/admin_dashboard.html')


@role_required('teacher')
def teacher_dashboard(request):
    return render(request, 'dashboards/teacher_dashboard.html')


@role_required('student')
def student_dashboard(request):
    return render(request, 'dashboards/student_dashboard.html')


@role_required('parent')
def parent_dashboard(request):
    return render(request, 'dashboards/parent_dashboard.html')
