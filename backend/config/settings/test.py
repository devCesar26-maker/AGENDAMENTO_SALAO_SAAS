"""Ambiente de testes: rápido, hermético e determinístico."""

from .base import *  # noqa: F403

DEBUG = False
PUBLIC_TENANT_HEADER_FALLBACK = True
MIDDLEWARE = [
    middleware
    for middleware in MIDDLEWARE  # noqa: F405
    if middleware != "whitenoise.middleware.WhiteNoiseMiddleware"
]

# Celery síncrono nos testes: assertions sobre efeitos colaterais funcionam direto.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# E-mail capturado em memória (django.core.mail.outbox).
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # rapidez apenas em teste

# Throttle desligado nos testes (cada teste tem sua asserção específica).
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_CLASSES": ()}  # noqa: F405

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# WhiteNoise manifest exige build de estáticos; nos testes usa storage simples.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

SECRET_KEY = "test-only-random-looking-signing-key-longer-than-thirty-two-bytes"
SIMPLE_JWT = {**SIMPLE_JWT, "SIGNING_KEY": SECRET_KEY}  # noqa: F405
