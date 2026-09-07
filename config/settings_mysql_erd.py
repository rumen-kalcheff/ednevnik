"""
Временен settings модул, използван само за да се генерира MySQL
копие на схемата (за ER диаграма в MySQL Workbench).
НЕ се използва за нормална работа на приложението — основната база остава PostgreSQL
(вж. settings.py). Пуска се изрично с:
    DJANGO_SETTINGS_MODULE=config.settings_mysql_erd python manage.py migrate
"""
from .settings import *  # noqa: F401,F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'ednevnik_erd',
        'USER': 'root',
        'PASSWORD': '',
        'HOST': '127.0.0.1',
        'PORT': '3307',
    }
}
