"""Ambiente de produção: endurecimento total, sem concessões."""

from .base import *  # noqa: F403
from .base import env, env_bool, env_int

DEBUG = False

# HTTPS obrigatório.
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

ALLOWED_HOSTS = [h.strip() for h in env("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()]
if not ALLOWED_HOSTS:
    raise RuntimeError("DJANGO_ALLOWED_HOSTS é obrigatório em produção.")
if env("DJANGO_SECRET_KEY", "").startswith("dev-only"):
    raise RuntimeError("DJANGO_SECRET_KEY de desenvolvimento detectada em produção.")

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
