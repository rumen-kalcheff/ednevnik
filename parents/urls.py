from django.urls import path
from . import views

urlpatterns = [
    path('grades/', views.grade_list, name='parent_grade_list'),
    path('absences/', views.absence_list, name='parent_absence_list'),
    path('schedule/', views.schedule, name='parent_schedule'),
    path('materials/', views.material_list, name='parent_material_list'),
    path('statistics/', views.statistics, name='parent_statistics'),
]
