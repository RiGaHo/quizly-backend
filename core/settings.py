"""Environment configuration with explicit development and production boundaries."""

from datetime import timedelta
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

from .utils import validate_origins

BASE_DIR = Path(__file__).resolve().parent.parent
env = environ.Env()
if env.bool("DJANGO_READ_DOTENV", default=True):
    environ.Env.read_env(BASE_DIR / ".env", overwrite=False)
DEBUG = env.bool("DJANGO_DEBUG", default=False)
SECRET_KEY = env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])
if not DEBUG and (len(SECRET_KEY) < 50 or not ALLOWED_HOSTS):
    raise ImproperlyConfigured("Production requires a strong key and explicit hosts.")
if "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("Wildcard hosts are not supported.")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "accounts_app",
    "quizzes_app",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "accounts_app.api.security.CookieOriginMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "core.urls"
WSGI_APPLICATION = "core.wsgi.application"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": env("DATABASE_PATH", default=str(BASE_DIR / "db.sqlite3")),
        "OPTIONS": {"timeout": 20},
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

CORS_ALLOWED_ORIGINS = env.list("FRONTEND_ORIGINS", default=[])
validate_origins(CORS_ALLOWED_ORIGINS, DEBUG)
CORS_ALLOW_CREDENTIALS = True
CORS_URLS_REGEX = r"^/api/.*$"
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS
COOKIE_SECURE = not DEBUG
COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = COOKIE_SECURE
CSRF_COOKIE_SECURE = COOKIE_SECURE
SESSION_COOKIE_HTTPONLY = True
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 0
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
if env.bool("TRUST_PROXY", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
DATA_UPLOAD_MAX_MEMORY_SIZE = 64 * 1024
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "accounts_app.api.authentication.CookieAuthentication"
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "UNAUTHENTICATED_USER": None,
}

AUTH_USER_MODEL = "accounts_app.User"

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": False,
}

# Credentials are optional at startup and resolved only by a generation request.
GEMINI_API_KEY = env("GEMINI_API_KEY", default="")
GEMINI_API_KEY_FILE = env("GEMINI_API_KEY_FILE", default="")
GENERATION_TIMEOUT = env.int("GENERATION_TIMEOUT", default=900)
GENERATION_LOCK_PATH = env(
    "GENERATION_LOCK_PATH", default="/tmp/quizly-generation.lock"
)
GENERATION_TEMP_DIR = env("GENERATION_TEMP_DIR", default=None)
GENERATION_OPTIONS = {
    "download": {
        "max_seconds": env.int("MAX_VIDEO_SECONDS", default=900),
        "max_bytes": env.int("MAX_DOWNLOAD_BYTES", default=100_000_000),
        "timeout": env.int("DOWNLOAD_TIMEOUT", default=120),
    },
    "audio": {
        "max_seconds": env.int("MAX_VIDEO_SECONDS", default=900),
        "timeout": env.int("AUDIO_TIMEOUT", default=120),
    },
    "whisper": {
        "model_name": env("WHISPER_MODEL", default="base"),
        "cache_directory": env("WHISPER_CACHE_DIR", default=str(BASE_DIR / "models")),
        "cpu_threads": env.int("WHISPER_CPU_THREADS", default=2),
        "max_chars": env.int("MAX_TRANSCRIPT_CHARS", default=120000),
    },
    "gemini": {
        "model": env("GEMINI_MODEL", default="gemini-3.8-flash"),
        "timeout": env.int("GEMINI_TIMEOUT", default=60),
    },
}
if GENERATION_TIMEOUT <= 0 or any(
    isinstance(value, int) and value <= 0
    for options in GENERATION_OPTIONS.values()
    for value in options.values()
):
    raise ImproperlyConfigured("Processing limits must be positive.")
