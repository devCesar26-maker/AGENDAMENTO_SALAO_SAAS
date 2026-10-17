from django.conf import settings
from django.test import RequestFactory, override_settings

from core.api.throttling import PublicBookingRateThrottle


def test_throttle_usa_remote_addr_quando_nao_ha_proxy_confiavel():
    rest_framework = {**settings.REST_FRAMEWORK, "NUM_PROXIES": 0}
    request = RequestFactory().get("/", HTTP_X_FORWARDED_FOR="198.51.100.1")
    request.META["REMOTE_ADDR"] = "192.0.2.10"

    with override_settings(REST_FRAMEWORK=rest_framework):
        assert PublicBookingRateThrottle().get_ident(request) == "192.0.2.10"
