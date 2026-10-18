"""Ambiente de produção: endurecimento total, sem concessões."""

from .base import *  # noqa: F403
from .base import (
    CORS_ALLOWED_ORIGINS,
    CSRF_TRUSTED_ORIGINS,
    DATABASES,
    PUBLIC_BASE_DOMAIN,
    REFRESH_TOKEN_COOKIE_SAMESITE,
    env,
    env_bool,
    env_int,
)

DEBUG = False
PUBLIC_TENANT_HEADER_FALLBACK = False

# HTTPS obrigatório.
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
REFRESH_TOKEN_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

ALLOWED_HOSTS = [
    h.strip() for h in env("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()
]
if env("PUBLIC_BASE_DOMAIN", "").strip():
    ALLOWED_HOSTS.append(f".{env('PUBLIC_BASE_DOMAIN').strip().lstrip('.')}")
if not ALLOWED_HOSTS:
    raise RuntimeError("DJANGO_ALLOWED_HOSTS é obrigatório em produção.")
if not PUBLIC_BASE_DOMAIN:
    raise RuntimeError("PUBLIC_BASE_DOMAIN é obrigatório em produção.")
if env("DJANGO_SECRET_KEY", "").startswith("dev-only"):
    raise RuntimeError("DJANGO_SECRET_KEY de desenvolvimento detectada em produção.")
if len(env("DJANGO_SECRET_KEY", "")) < 50 or len(set(env("DJANGO_SECRET_KEY", ""))) < 5:
    raise RuntimeError(
        "DJANGO_SECRET_KEY deve ter ao menos 50 caracteres aleatórios em produção."
    )
if not env("DATABASE_URL", "").strip():
    raise RuntimeError("DATABASE_URL é obrigatório em produção.")
if not DATABASES["default"]["ENGINE"].endswith("postgresql"):
    raise RuntimeError("Produção exige PostgreSQL.")
if DATABASES["default"].get("HOST", "").lower() in {"localhost", "127.0.0.1"}:
    raise RuntimeError("DATABASE_URL deve apontar para PostgreSQL remoto em produção.")
if not env_bool("DB_SSL_REQUIRE", False) or DATABASES["default"].get("OPTIONS", {}).get(
    "sslmode"
) not in {"require", "verify-ca", "verify-full"}:
    raise RuntimeError(
        "DB_SSL_REQUIRE=1 e sslmode seguro são obrigatórios em produção."
    )
if not env("REDIS_URL", "").strip() or "localhost" in env("REDIS_URL", "").lower():
    raise RuntimeError("REDIS_URL remoto é obrigatório em produção.")
if (
    not env("CELERY_BROKER_URL", "").strip()
    or "localhost" in env("CELERY_BROKER_URL", "").lower()
):
    raise RuntimeError("CELERY_BROKER_URL remoto é obrigatório em produção.")
try:
    trusted_proxy_count = int(env("DRF_NUM_PROXIES", ""))
except ValueError as exc:
    raise RuntimeError("DRF_NUM_PROXIES deve ser um inteiro não negativo.") from exc
if trusted_proxy_count < 0:
    raise RuntimeError("DRF_NUM_PROXIES deve ser um inteiro não negativo.")
if not CORS_ALLOWED_ORIGINS or any(
    not origin.startswith("https://") for origin in CORS_ALLOWED_ORIGINS
):
    raise RuntimeError(
        "CORS_ALLOWED_ORIGINS deve listar origens HTTPS explícitas em produção."
    )
if not CSRF_TRUSTED_ORIGINS or any(
    not origin.startswith("https://") for origin in CSRF_TRUSTED_ORIGINS
):
    raise RuntimeError(
        "CSRF_TRUSTED_ORIGINS deve listar origens HTTPS explícitas em produção."
    )
if not env("FRONTEND_URL", "").startswith("https://"):
    raise RuntimeError("FRONTEND_URL HTTPS é obrigatório em produção.")
if REFRESH_TOKEN_COOKIE_SAMESITE not in {"Lax", "Strict", "None"}:
    raise RuntimeError("REFRESH_TOKEN_COOKIE_SAMESITE deve ser Lax, Strict ou None.")

EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
if EMAIL_BACKEND != "django.core.mail.backends.smtp.EmailBackend":
    raise RuntimeError("Produção deve usar o backend SMTP transacional configurado.")
EMAIL_HOST = env("BREVO_SMTP_HOST", "smtp-relay.brevo.com")
EMAIL_PORT = env_int("BREVO_SMTP_PORT", 587)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = env("BREVO_SMTP_LOGIN", "")
EMAIL_HOST_PASSWORD = env("BREVO_SMTP_PASSWORD", "")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "")
if EMAIL_BACKEND.endswith("smtp.EmailBackend") and not all(
    (EMAIL_HOST_USER, EMAIL_HOST_PASSWORD, DEFAULT_FROM_EMAIL)
):
    raise RuntimeError(
        "BREVO_SMTP_LOGIN, BREVO_SMTP_PASSWORD e DEFAULT_FROM_EMAIL são obrigatórios em produção."
    )
