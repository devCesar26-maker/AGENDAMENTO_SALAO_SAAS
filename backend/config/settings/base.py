"""
Configuração base do Éclat Studio.

Compartilhada por todos os ambientes (dev, test, prod). Segredos e ajustes por
ambiente vêm exclusivamente de variáveis de ambiente (ver .env.example).
"""

import os
from datetime import timedelta
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Em dev/test carrega backend/.env se existir; em prod as variáveis vêm do host.
if os.environ.get("DJANGO_SETTINGS_MODULE", "").endswith(".dev"):
    load_dotenv(BASE_DIR / ".env")

PROJECT_NAME = "Éclat Studio"


def env(key: str, default=None):
    return os.environ.get(key, default)


def env_bool(key: str, default: bool = False) -> bool:
    return env(key, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_int(key: str, default: int) -> int:
    try:
        return int(env(key, default))
    except (TypeError, ValueError):
        return default


SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    "dev-only-insecure-key-troque-em-producao-pelo-env",
)
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = [
    h.strip() for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()
]
PUBLIC_BASE_DOMAIN = env("PUBLIC_BASE_DOMAIN", "")
if PUBLIC_BASE_DOMAIN.strip():
    ALLOWED_HOSTS.append(f".{PUBLIC_BASE_DOMAIN.strip().lstrip('.')}")

# Aplicativos
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]
THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "drf_spectacular_sidecar",  # assets do Swagger UI locais, servidos via staticfiles
    "drf_spectacular",
    "corsheaders",
    "csp",
]
LOCAL_APPS = [
    "core",
    "accounts",
    "organizations",
    "catalog",
    "customers",
    "scheduling",
    "billing",
    "notifications",
    "analytics",
]
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "organizations.middleware.PublicBookingTenantMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "csp.middleware.CSPMiddleware",
    "core.api.exceptions.ExceptionFormatMiddleware",
]

if DEBUG:
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# Banco de dados — exclusivamente via DATABASE_URL (PostgreSQL).
DATABASES = {
    "default": dj_database_url.parse(
        env("DATABASE_URL", "postgres://ecalt:ecalt@localhost:5432/ecalt"),
        conn_max_age=env_int("DB_CONN_MAX_AGE", 60),
        ssl_require=env_bool("DB_SSL_REQUIRE", False),
    )
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

# Senhas: Argon2 + validadores.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internacionalização (pt-BR, BRL, fuso configurável por salão).
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

# i18n de moeda no formato BRL (usado em templates/e-mails; frontend formata com Intl).
NUMBER_GROUPING = 3
DECIMAL_SEPARATOR = ","
THOUSAND_SEPARATOR = "."

# Estáticos (WhiteNoise).
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# DRF: JWT obrigatório exceto rotas públicas; erros em formato único.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "core.api.pagination.DefaultPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Configure com o número de proxies confiáveis. O ingress deve sobrescrever
    # X-Forwarded-For antes de encaminhar ao Django.
    "NUM_PROXIES": env_int("DRF_NUM_PROXIES", 0),
    "DEFAULT_THROTTLE_CLASSES": ("core.api.throttling.RoleUserRateThrottle",),
    "DEFAULT_THROTTLE_RATES": {
        "user": "600/min",
        "auth": "10/min",
        "public_booking": "10/h",
    },
    "EXCEPTION_HANDLER": "core.api.exceptions.exception_handler",
}
PUBLIC_TENANT_HEADER_FALLBACK = env_bool("PUBLIC_TENANT_HEADER_FALLBACK", False)

# SimpleJWT: access curto em memória; refresh longo com rotação e blacklist.
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env_int("JWT_ACCESS_MINUTES", 15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env_int("JWT_REFRESH_DAYS", 7)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "TOKEN_OBTAIN_SERIALIZER": "core.api.jwt.TenantTokenObtainPairSerializer",
}

# Bloqueio temporário de login por e-mail após falhas (anti brute force).
LOGIN_MAX_FAILED_ATTEMPTS = env_int("LOGIN_MAX_FAILED_ATTEMPTS", 5)
LOGIN_LOCKOUT_SECONDS = env_int("LOGIN_LOCKOUT_SECONDS", 900)  # 15 minutos

# drf-spectacular
SPECTACULAR_SETTINGS = {
    "TITLE": "Éclat Studio API",
    "DESCRIPTION": "API de agendamento e gestão para salões de beleza e barbearias.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": "/api/v1",
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
}

# CORS restrito ao frontend.
CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in env("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if o.strip()
]
CORS_ALLOW_CREDENTIALS = True

# Cookies (refresh JWT e futura sessão de admin).
SESSION_COOKIE_SECURE = env_bool("COOKIE_SECURE", False)
CSRF_COOKIE_SECURE = env_bool("COOKIE_SECURE", False)
REFRESH_TOKEN_COOKIE_NAME = env("REFRESH_TOKEN_COOKIE_NAME", "refresh")
REFRESH_TOKEN_COOKIE_PATH = env("REFRESH_TOKEN_COOKIE_PATH", "/api/v1/auth/")
REFRESH_TOKEN_COOKIE_DOMAIN = env("REFRESH_TOKEN_COOKIE_DOMAIN", "") or None
REFRESH_TOKEN_COOKIE_SECURE = env_bool(
    "REFRESH_TOKEN_COOKIE_SECURE", env_bool("COOKIE_SECURE", False)
)
REFRESH_TOKEN_COOKIE_SAMESITE = env("REFRESH_TOKEN_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_HTTPONLY = False  # frontend precisa ler o token para POSTs com cookie
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in env("CSRF_TRUSTED_ORIGINS", "http://localhost:5173").split(",") if o.strip()
]
SESSION_COOKIE_HTTPONLY = True

# Segurança de transporte/config (reforçadas em prod).
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# CSP restritiva (django-csp 4.x permite múltiplas diretrizes via tuplas).
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ("'self'",),
        "script-src": ("'self'",),
        "style-src": ("'self'",),
        "img-src": ("'self'", "data:"),
        "font-src": ("'self'",),
        "connect-src": ("'self'",),
        "frame-ancestors": ("'none'",),
        "base-uri": ("'self'",),
        "form-action": ("'self'",),
        "object-src": ("'none'",),
    }
}

# Celery
CELERY_BROKER_URL = env("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", env("REDIS_URL", "redis://localhost:6379/0"))
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TASK_ACKS_LATE = True
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    "lembretes-24h": {
        "task": "notifications.tasks.send_appointment_reminders",
        "schedule": env_int("REMINDER_CRON_SECONDS", 900),  # a cada 15 min
    },
    "notification-outbox": {
        "task": "notifications.tasks.dispatch_notification_outbox",
        "schedule": env_int("OUTBOX_CRON_SECONDS", 30),
    },
    "ofertas-espera-expiradas": {
        "task": "notifications.tasks.expire_waitlist_offers",
        "schedule": env_int("WAITLIST_OFFER_CRON_SECONDS", 60),
    },
    "sugestoes-expiradas": {
        "task": "notifications.tasks.expire_suggested_appointments",
        "schedule": env_int("SUGGESTION_CRON_SECONDS", 300),
    },
    "sugestoes-recorrencia": {
        "task": "scheduling.tasks.generate_recurring_suggestions_for_active_organizations",
        "schedule": env_int("RECURRING_CRON_SECONDS", 86400),
    },
    "flash-slots": {
        "task": "scheduling.tasks.generate_flash_slots_for_active_organizations",
        "schedule": env_int("FLASH_SLOT_CRON_SECONDS", 21600),
    },
    "flash-slots-recalculo": {
        "task": "scheduling.tasks.refresh_flash_slot_prices",
        "schedule": env_int("FLASH_REFRESH_CRON_SECONDS", 3600),
    },
    "flash-slots-expiracao": {
        "task": "scheduling.tasks.expire_flash_slots",
        "schedule": env_int("FLASH_EXPIRE_CRON_SECONDS", 900),
    },
}

# E-mail: settings.dev usa Mailhog por padrão; settings.test usa locmem.
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "mailhog")
EMAIL_PORT = env_int("EMAIL_PORT", 1025)
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", False)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "Éclat Studio <nao-responda@ecalt.local>")

# Frontend URL (links em e-mails e página pública).
FRONTEND_URL = env("FRONTEND_URL", "http://localhost:5173")
RATING_TOKEN_DAYS = env_int("RATING_TOKEN_DAYS", 7)
RECURRING_SUGGESTION_HOURS = env_int("RECURRING_SUGGESTION_HOURS", 48)

# Rate limit do Redis (Django >= 5.1 cache-based throttling também suportado).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL", "redis://localhost:6379/1"),
    }
}

# Mercado Pago: sandbox credentials are injected via environment only.
MP_ACCESS_TOKEN = env("MP_ACCESS_TOKEN", "")
MP_PUBLIC_KEY = env("MP_PUBLIC_KEY", "")
MP_WEBHOOK_SECRET = env("MP_WEBHOOK_SECRET", "")

# Marketplace (split de assinatura): OAuth da conta Mercado Pago do salão.
# A comissão da plataforma é um percentual por salão (Organization), com este
# padrão global. Em sandbox o split exige contas de teste; em produção exige KYC
# e aprovação de marketplace no Mercado Pago.
MP_CLIENT_ID = env("MP_CLIENT_ID", "")
MP_CLIENT_SECRET = env("MP_CLIENT_SECRET", "")
MP_OAUTH_REDIRECT_URI = env("MP_OAUTH_REDIRECT_URI", "")
MP_AUTHORIZATION_URL = env("MP_AUTHORIZATION_URL", "https://auth.mercadopago.com.br/authorization")
MP_OAUTH_TOKEN_URL = env("MP_OAUTH_TOKEN_URL", "https://api.mercadopago.com/oauth/token")
PLATFORM_FEE_DEFAULT_PERCENT = env_int("PLATFORM_FEE_DEFAULT_PERCENT", 10)

# Sanitização de texto livre (XSS em observações etc.).
SANITIZE_ALLOWLIST_TAGS = ("b", "i", "em", "strong", "br", "p")

# Logging sem dados pessoais sensíveis.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "{levelname} {asctime} {name} {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.db.backends": {"level": "WARNING"},
        "ecalt": {"level": "INFO"},
    },
}
