from django.urls import path
from . import views

urlpatterns = [
    # Оценки
    path('grades/', views.grade_list, name='grade_list'),
    path('grades/add/', views.grade_add, name='grade_add'),
    path('grades/bulk/', views.grade_bulk, name='grade_bulk'),
    path('grades/<int:pk>/edit/', views.grade_edit, name='grade_edit'),
    path('grades/<int:pk>/delete/', views.grade_delete, name='grade_delete'),
    # Отсъствия
    path('absences/', views.absence_list, name='absence_list'),
    path('absences/add/', views.absence_add, name='absence_add'),
    path('absences/<int:pk>/edit/', views.absence_edit, name='absence_edit'),
    path('absences/<int:pk>/delete/', views.absence_delete, name='absence_delete'),
    # Материали
    path('materials/', views.material_list, name='teacher_material_list'),
    path('materials/upload/', views.material_upload, name='material_upload'),
    path('materials/<int:pk>/edit/', views.material_edit, name='material_edit'),
    path('materials/<int:pk>/delete/', views.material_delete, name='material_delete'),
    # Статистики
    path('statistics/', views.statistics, name='teacher_statistics'),
    # Класен ръководител
    path('homeroom/', views.homeroom_overview, name='homeroom_overview'),
    path('homeroom/absences/<int:pk>/excuse/', views.homeroom_absence_excuse,
         name='homeroom_absence_excuse'),
    # Профил
    path('profile/', views.my_profile, name='teacher_profile'),
    # Контакти
    path('parent-contacts/', views.parent_contacts, name='parent_contacts'),
    path('student-contacts/', views.student_contacts, name='student_contacts'),
    # AJAX
    path('api/students-by-class/', views.students_by_class, name='students_by_class'),
]
