from django.urls import path
from . import views

urlpatterns = [
    path('grades/', views.grade_list, name='parent_grade_list'),
    path('absences/', views.absence_list, name='parent_absence_list'),
    path('materials/', views.material_list, name='parent_material_list'),
    path('profile/', views.my_profile, name='parent_profile'),
    path('statistics/', views.statistics, name='parent_statistics'),
    path('teacher-contacts/', views.teacher_contacts, name='parent_teacher_contacts'),
]
