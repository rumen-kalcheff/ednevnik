from pathlib import Path
from decouple import config
from django.contrib.messages import constants as message_constants

BASE_DIR = Path(__file__).resolve().parent.parent

# Чете се от .env файла — никога не е директно в кода
SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = ['localhost', '127.0.0.1']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Наши приложения
    'accounts',
    'school',
    'students',
    'teachers',
    'adminpanel',
    'grades',
    'materials',
    'parents',
    'timetable',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

# Templates — Django търси HTML файловете в папка templates/ в корена на проекта
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# База данни — PostgreSQL, настройките идват от .env
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD', default=''),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'accounts.validators.BgUserAttributeSimilarityValidator'},
    {'NAME': 'accounts.validators.BgMinimumLengthValidator'},
    {'NAME': 'accounts.validators.BgNumericPasswordValidator'},
]

# Интерфейс на български, часова зона България
LANGUAGE_CODE = 'bg'
TIME_ZONE = 'Europe/Sofia'
USE_I18N = True
USE_TZ = True

# Статични файлове (CSS, JS, изображения за дизайна)
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Медийни файлове (качени учебни материали, снимки)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Казваме на Django да използва нашия User модел вместо вградения
AUTH_USER_MODEL = 'accounts.User'

# Пренасочване след login/logout
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/login/'

# Django нарича нивото "error", а Bootstrap няма alert-error, само alert-danger —
# без тази замяна съобщенията от messages.error() излизат нестилизирани.
MESSAGE_TAGS = {
    message_constants.ERROR: 'danger',
}

# Имейл — настройките идват от .env
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default=EMAIL_HOST_USER)
# Таван на изчакването за връзка с пощенския сървър — без него бавен или
# недостъпен SMTP може да блокира заявката за неограничено време.
EMAIL_TIMEOUT = config('EMAIL_TIMEOUT', default=10, cast=int)

# Линкът за възстановяване на парола е валиден 24 часа (по подразбиране в Django е 3 дни)
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24

# Автоматично прекъсване на сесия след 2 часа неактивност (НФИ4)
SESSION_COOKIE_AGE = 7200
SESSION_SAVE_EVERY_REQUEST = True
