"""Parte 3: o contador de throttling precisa viver no Redis, não em memória.

Nota: as rates do DRF são congeladas no import (rest_framework.throttling
usa `api_settings.DEFAULT_THROTTLE_RATES` capturado na definição de classe),
então sobrescrever REST_FRAMEWORK via override_settings NÃO muda a taxa
efetiva. Fixamos a taxa direto em PublicBookingRateThrottle.rate no teste.
"""

import pytest
import redis as redis_lib
from django.test import override_settings
from django.urls import reverse

from core.api.throttling import PublicBookingRateThrottle

REDIS_TEST_LOCATION = "redis://localhost:6379/15"
REDIS_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_TEST_LOCATION,
    }
}


def _redis_test_client():
    return redis_lib.Redis.from_url(REDIS_TEST_LOCATION)


def public_headers(organization):
    """Mesma convenção da API pública de reserva: slug da org em cabeçalho."""
    return {"HTTP_X_TENANT_SLUG": organization.slug}


@pytest.mark.django_db
@override_settings(CACHES=REDIS_CACHE)
def test_contador_do_throttle_publico_vive_no_redis_e_dispara_429(
    api_client, organization, monkeypatch
):
    from scheduling.tests.test_public_booking import make_public_schedule

    make_public_schedule(organization)
    monkeypatch.setattr(PublicBookingRateThrottle, "rate", "2/min", raising=False)
    _redis_test_client().flushdb()

    statuses = [
        api_client.get(reverse("public-catalog"), **public_headers(organization)).status_code
        for _ in range(3)
    ]
    assert statuses[:2] == [200, 200]
    assert statuses[2] == 429

    keys = _redis_test_client().keys("*throttle*")
    assert keys, "o contador de throttling deveria estar armazenado no Redis"
    assert any(b"public_booking" in key for key in keys)

    # Cleanup so the test doesn't contaminate other processes on DB 15.
    _redis_test_client().flushdb()
