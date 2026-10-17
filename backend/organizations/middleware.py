"""Resolução do tenant pelo subdomínio nas rotas públicas de reserva."""

from django.conf import settings
from django.http import HttpResponseNotFound
from django.utils.text import slugify

from organizations.models import Organization


class PublicBookingTenantMiddleware:
    """Resolve o tenant das páginas /b/ e da API pública de reserva."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        is_booking_page = request.path == "/b" or request.path.startswith("/b/")
        is_public_api = request.path.startswith("/api/v1/public/")
        if not (is_booking_page or is_public_api):
            return self.get_response(request)

        domain = getattr(settings, "PUBLIC_BASE_DOMAIN", "").strip().lower().lstrip(".")
        host = request.get_host().split(":", 1)[0].lower().rstrip(".")
        suffix = f".{domain}" if domain else ""
        slug = None
        if suffix and host.endswith(suffix):
            candidate = host[: -len(suffix)]
            if candidate and "." not in candidate and candidate not in {"app", "www"}:
                slug = candidate

        # Desenvolvimento local não tem subdomínio: /b/<slug>/ identifica a
        # página e seu cliente envia o mesmo slug em X-Tenant-Slug à API.
        if slug is None and is_booking_page:
            slug = request.path.strip("/").split("/")[1:2]
            slug = slug[0] if slug else None
        if slug is None and is_public_api:
            slug = request.headers.get("X-Tenant-Slug")

        if slug is None or slugify(slug) != slug:
            return HttpResponseNotFound("Organização não encontrada para esta página pública.")
        try:
            request.organization = Organization.objects.get(slug=slug, is_active=True)
        except Organization.DoesNotExist:
            return HttpResponseNotFound("Organização não encontrada para esta página pública.")
        return self.get_response(request)
