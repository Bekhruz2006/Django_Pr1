from dotenv import load_dotenv
import os
from pathlib import Path
from django.utils.translation import gettext_lazy as _

load_dotenv()
BASE_DIR = Path(__file__).resolve().parents[1]


ROSETTA_EXCLUDED_PATHS = (
    os.path.join(BASE_DIR, 'venv'),
    os.path.join(BASE_DIR, 'env'),
)


LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False, 
    'formatters': {
        'verbose': {
            'format': '--- [{asctime}] {levelname} ---\nМодуль: {module}\n{message}\n',
            'style': '{',
        },
        'simple': {
            'format': '[{asctime}] {levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'error_file': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'error.log',
            'maxBytes': 1024 * 1024 * 10,
            'backupCount': 5,             
            'formatter': 'verbose',
            'encoding': 'utf-8',          
        },
        'debug_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'debug.log',
            'maxBytes': 1024 * 1024 * 15, # 15 MB
            'backupCount': 3,
            'formatter': 'simple',
            'encoding': 'utf-8',
        },
    },
    'loggers': {
        'django.request': {
            'handlers': ['error_file'],
            'level': 'ERROR',
            'propagate': False,
        },
        'schedule': {
            'handlers':['debug_file', 'error_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'accounts': {'handlers':['debug_file', 'error_file'], 'level': 'INFO', 'propagate': False},
        'journal': {'handlers':['debug_file', 'error_file'], 'level': 'INFO', 'propagate': False},
        'lms': {'handlers': ['debug_file', 'error_file'], 'level': 'INFO', 'propagate': False},
    },
}

LANGUAGES = [
    ('ru', _('Русский')),
    ('tg', _('Тоҷикӣ')),
    ('en', _('English')),
]

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-development-only')

DEBUG = os.environ.get('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'accounts.apps.AccountsConfig',      
    'journal.apps.JournalConfig',  
    'schedule.apps.ScheduleConfig',      
    'news.apps.NewsConfig',             
    'chat.apps.ChatConfig',             
    'core.apps.CoreConfig',    
    'rosetta', 
    'lms.apps.LmsConfig',
    'testing.apps.TestingConfig',
     
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', 
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'department_platform.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.template.context_processors.i18n',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.global_notifications',
            ],
        },
    },
]

WSGI_APPLICATION = 'department_platform.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'university_db',  
        'USER': 'root',           
        'PASSWORD': '1234',          
        'HOST': '127.0.0.1',
        'PORT': '3306',
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            'charset': 'utf8mb4',
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'ru-ru'
LOCALE_PATHS = [
    BASE_DIR / 'locale',
]

TIME_ZONE = 'Asia/Dushanbe'

USE_I18N = True

USE_TZ = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CSRF_TRUSTED_ORIGINS = ['https://*.ngrok-free.app']
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'accounts.User'

LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'core:dashboard'
LOGOUT_REDIRECT_URL = 'accounts:login'

FILE_UPLOAD_MAX_MEMORY_SIZE = 104857600  
DATA_UPLOAD_MAX_MEMORY_SIZE = 104857600  

SESSION_COOKIE_AGE = 36000

SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False') == 'True'

CSRF_COOKIE_SECURE = os.environ.get('CSRF_COOKIE_SECURE', 'False') == 'True'

SESSION_SAVE_EVERY_REQUEST = True

SESSION_EXPIRE_AT_BROWSER_CLOSE = True

