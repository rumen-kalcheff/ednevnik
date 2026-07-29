from django.urls import path
from . import views

urlpatterns = [
    # Табло и настройки
    path('', views.dashboard, name='timetable_dashboard'),
    path('settings/', views.settings_view, name='timetable_settings'),
    # Учебни зали
    path('rooms/', views.room_list, name='room_list'),
    path('rooms/create/', views.room_create, name='room_create'),
    path('rooms/<int:pk>/edit/', views.room_edit, name='room_edit'),
    path('rooms/<int:pk>/delete/', views.room_delete, name='room_delete'),
    # Смени и чужди езици по класове
    path('classes/', views.class_settings, name='timetable_class_settings'),
    # Седмичен хорариум
    path('curriculum/', views.curriculum, name='timetable_curriculum'),
    # Разписание
    path('grid/', views.grid, name='timetable_grid'),
    path('grid/<int:pk>/edit-draft/', views.start_editing, name='timetable_start_editing'),
    path('version/<int:pk>/publish/', views.publish_version, name='timetable_publish'),
    path('version/<int:pk>/discard/', views.discard_draft, name='timetable_discard_draft'),
    path('lesson/add/', views.lesson_add, name='lesson_add'),
    path('lesson/<int:pk>/edit/', views.lesson_edit, name='lesson_edit'),
    path('lesson/<int:pk>/delete/', views.lesson_delete, name='lesson_delete'),
    # Разписание по преподавател
    path('teachers/', views.teacher_grid, name='timetable_teacher_grid'),
    # Отсъствия на преподаватели
    path('absences/', views.absence_list, name='teacher_absence_list'),
    path('absences/<int:pk>/status/', views.absence_status, name='teacher_absence_status'),
    path('absences/<int:pk>/delete/', views.absence_delete, name='teacher_absence_delete'),
    path('absences/<int:pk>/affected/', views.absence_affected, name='teacher_absence_affected'),
    # Замествания
    path('substitutions/', views.substitution_day, name='substitution_day'),
    path('substitutions/save/', views.substitution_save, name='substitution_save'),
    # Дневник на действията
    path('log/', views.log_list, name='timetable_log'),
]
