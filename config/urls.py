from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from accounts.views import home_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home_view, name='home'),
    path('', include('accounts.urls')),
    path('admin-panel/', include('adminpanel.urls')),
    path('admin-panel/timetable/', include('timetable.urls')),
    path('teacher/', include('teachers.urls')),
    path('student/', include('students.urls')),
    path('parent/', include('parents.urls')),
]

# Обслужване на качени файлове (учебни материали) при разработка
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
