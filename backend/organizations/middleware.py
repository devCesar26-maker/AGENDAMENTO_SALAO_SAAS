"""Resolução do tenant pelo subdomínio nas rotas públicas de reserva."""

from django.conf import settings
from django.http import HttpResponseNotFound

from organizations.models import Organization


class PublicBookingTenantMiddleware:
    """Anexa ``request.organization`` em /b/ com base em ``<slug>.base-domain``."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/b" or request.path.startswith("/b/"):
            domain = getattr(settings, "PUBLIC_BASE_DOMAIN", "").strip().lower().lstrip(".")
            host = request.get_host().split(":", 1)[0].lower().rstrip(".")
            suffix = f".{domain}" if domain else ""
            if not domain or not host.endswith(suffix):
                return HttpResponseNotFound("Organização não encontrada para este subdomínio.")
            slug = host[: -len(suffix)]
            if not slug or "." in slug:
                return HttpResponseNotFound("Organização não encontrada para este subdomínio.")
            try:
                request.organization = Organization.objects.get(slug=slug)
            except Organization.DoesNotExist:
                return HttpResponseNotFound("Organização não encontrada para este subdomínio.")
        return self.get_response(request)
