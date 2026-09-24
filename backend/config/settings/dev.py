"""Ambiente de desenvolvimento (docker compose local)."""

from .base import *  # noqa: F403
from .base import env, env_bool, env_int

DEBUG = env_bool("DJANGO_DEBUG", True)

# django-debug-toolbar apenas em dev (valida N+1 manualmente; testes usam assert).
INTERNAL_IPS = ["127.0.0.1"]
if "debug_toolbar" not in INSTALLED_APPS:  # noqa: F405
    INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405

# Celery síncrono facilita o desenvolvimento local.
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_EAGER", True)

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", "mailhog")
EMAIL_PORT = env_int("EMAIL_PORT", 1025)
