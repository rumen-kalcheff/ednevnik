from django.urls import path
from . import views

urlpatterns = [
    path('schedule/', views.schedule, name='student_schedule'),
    path('grades/', views.grade_list, name='student_grade_list'),
    path('absences/', views.absence_list, name='student_absence_list'),
    path('materials/', views.material_list, name='student_material_list'),
    path('statistics/', views.statistics, name='student_statistics'),
    path('class/', views.class_info, name='student_class_info'),
    path('teacher-contacts/', views.teacher_contacts, name='student_teacher_contacts'),
]
