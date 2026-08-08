"""
Django settings for rental project.

Production-ready configuration:
- All secrets read from environment variables (or a .env file in the project root)
- DEBUG defaults to False
- CORS restricted to configured origins
- Static files served via WhiteNoise
- Optional production security hardening flags

To configure, copy .env.example to .env and fill in your real values.
"""

import os
from pathlib import Path

import environ

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# ------------------------------------------------------------------
# Environment variables (loads .env from the project root)
# ------------------------------------------------------------------
env = environ.Env(
    DEBUG=(bool, False),
    SECRET_KEY=(str, ''),
    ALLOWED_HOSTS=(list, ['localhost', '127.0.0.1', 'lexnul.alwaysdata.net']),
    CORS_ALLOWED_ORIGINS=(list, ['https://lexnul.alwaysdata.net']),
    CSRF_TRUSTED_ORIGINS=(list, []),
    DB_ENGINE=(str, 'django.db.backends.sqlite3'),
    DB_NAME=(str, str(BASE_DIR / 'db.sqlite3')),
    DB_HOST=(str, 'localhost'),
    DB_PORT=(str, '3306'),
    DB_USER=(str, 'root'),
    DB_PASSWORD=(str, ''),
)
# Read .env if present (development convenience). In production, set real
# environment variables instead — .env is git-ignored so secrets stay safe.
environ.Env.read_env(BASE_DIR / '.env')

# SECURITY WARNING: keep the secret key used in production secret!
# A random key is generated at runtime ONLY as a last resort for `manage.py`
# tooling in dev. Set SECRET_KEY in your .env / environment for real use.
SECRET_KEY = env('SECRET_KEY') or os.urandom(64).hex()

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env('DEBUG')

ALLOWED_HOSTS = env('ALLOWED_HOSTS')

# Custom user model — centralized in core app (NOT landlord)
AUTH_USER_MODEL = 'core.User'

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third party
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',   # Fixed
    'drf_spectacular',
    'corsheaders',

    # Local apps
    'core',
    'landlord',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'rental.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'rental.wsgi.application'


# ------------------------------------------------------------------
# Database — configure via env (MySQL in production)
# ------------------------------------------------------------------
# DATABASES = {
#     'default': {
#         'ENGINE': env('DB_ENGINE'),
#         'NAME': env('DB_NAME'),
#         'HOST': env('DB_HOST'),
#         'PORT': env('DB_PORT'),
#         'USER': env('DB_USER'),
#         'PASSWORD': env('DB_PASSWORD'),
#         'OPTIONS': {
#             'charset': 'utf8mb4',
#         } if env('DB_ENGINE') == 'django.db.backends.mysql' else {},
#     }
# }
DATABASES = {
    'default': {
        'ENGINE': "django.db.backends.mysql",
        'NAME': "lexnul_rental",
        'HOST': "mysql-lexnul.alwaysdata.net",
        'USER': "lexnul",
        'PASSWORD': "mwalish",
        'OPTIONS': {
            'charset': 'utf8mb4',
        } if env('DB_ENGINE') == 'django.db.backends.mysql' else {},
    }
}
# --- Database (MySQL in production) ---
# DB_ENGINE=
# DB_NAME=lexnul_rental
# DB_HOST=mysql-lexnul.alwaysdata.net
# DB_PORT=3306
# DB_USER=
# DB_PASSWORD=mwalish


# ------------------------------------------------------------------
# Password validation
# ------------------------------------------------------------------
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


# ------------------------------------------------------------------
# Internationalization
# ------------------------------------------------------------------
LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Africa/Nairobi'

USE_I18N = True

USE_TZ = True


# ------------------------------------------------------------------
# Static & Media files
# ------------------------------------------------------------------
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# WhiteNoise — serve static files in production without a CDN.
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ====================== REST FRAMEWORK ======================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}
from datetime import timedelta

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=120),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=10),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,

    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',

    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

# ====================== AFRICA'S TALKING SMS SETTINGS ======================
AFRICAS_TALKING_USERNAME = env('AFRICAS_TALKING_USERNAME', default='sandbox')
AFRICAS_TALKING_API_KEY = env('AFRICAS_TALKING_API_KEY', default='')
AFRICAS_TALKING_SENDER_ID = env('AFRICAS_TALKING_SENDER_ID', default='RENTAL')

# ====================== MPESA SETTINGS ======================
MPESA_CONSUMER_KEY = env('MPESA_CONSUMER_KEY', default='')
MPESA_CONSUMER_SECRET = env('MPESA_CONSUMER_SECRET', default='')
MPESA_SHORTCODE = env('MPESA_SHORTCODE', default='174379')
MPESA_PASSKEY = env('MPESA_PASSKEY', default='')
MPESA_CALLBACK_URL = env('MPESA_CALLBACK_URL', default='')

# ====================== EMAIL SETTINGS ======================
# Default: console backend — prints emails to the terminal in development so the
# email OTP flow works with ZERO external credentials. For real delivery, set
# EMAIL_BACKEND=smtp + the EMAIL_HOST/PORT/USER/PASSWORD vars in your .env.
EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = env('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='Smart Rental System <noreply@smartrent.local>')

# ====================== PASSWORD RESET SETTINGS ======================
PASSWORD_RESET_CODE_LENGTH = 6
PASSWORD_RESET_CODE_EXPIRE_MINUTES = 15

# ====================== CORS ======================
# Development default: allow all origins (useful for local Vite dev server).
# In production set CORS_ALLOWED_ORIGINS in your .env, e.g.
#   CORS_ALLOWED_ORIGINS=https://app.example.com,https://www.example.com
cors_origins = env('CORS_ALLOWED_ORIGINS')
if cors_origins:
    CORS_ALLOW_ALL_ORIGINS = False
    CORS_ALLOWED_ORIGINS = cors_origins
else:
    CORS_ALLOW_ALL_ORIGINS = DEBUG
    CORS_ALLOWED_ORIGINS = []

# Trusted CSRF origins — required for the Django admin and any POST/CSRF flows
# when the site is served over HTTPS on alwaysdata.
CSRF_TRUSTED_ORIGINS = env('CSRF_TRUSTED_ORIGINS')

# ====================== PRODUCTION SECURITY HARDENING ======================
# These are enabled when DEBUG is False. Adjust via env if your deployment
# terminates TLS elsewhere (e.g. behind a reverse proxy / load balancer).
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = env('SECURE_SSL_REDIRECT', default=True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_REFERRER_POLICY = 'same-origin'

# Logging — capture M-Pesa callback issues and general server errors.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': env('DJANGO_LOG_LEVEL', default='INFO'),
            'propagate': False,
        },
    },
}

