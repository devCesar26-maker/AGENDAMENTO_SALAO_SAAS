"""Ambiente de desenvolvimento (docker compose local)."""

from .base import *  # noqa: F403
from .base import env, env_bool, env_int

DEBUG = env_bool("DJANGO_DEBUG", True)

# django-debug-toolbar apenas em dev (valida N+1 manualmente; testes usam assert).
INTERNAL_IPS = ["127.0.0.1"]
if "debug_toolbar" not in INSTALLED_APPS:  # noqa: F405
    INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405

# E-mails e notificações não podem bloquear requisições HTTP; testes ativam eager em test.py.
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_EAGER", False)

EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "mailhog")
EMAIL_PORT = env_int("EMAIL_PORT", 1025)
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", False)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
