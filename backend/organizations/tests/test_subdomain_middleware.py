import pytest
from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from organizations.factories import OrganizationFactory
from organizations.middleware import PublicBookingTenantMiddleware


@pytest.mark.django_db
@override_settings(PUBLIC_BASE_DOMAIN="eclatstudio.com.br", ALLOWED_HOSTS=[".eclatstudio.com.br"])
def test_resolve_organization_from_simulated_host():
    organization = OrganizationFactory(slug="eclat-studio-cesar")
    request = RequestFactory().get("/b/", HTTP_HOST="eclat-studio-cesar.eclatstudio.com.br")
    response = PublicBookingTenantMiddleware(lambda req: HttpResponse(str(req.organization.pk)))(
        request
    )
    assert response.status_code == 200
    assert response.content.decode() == str(organization.pk)


@pytest.mark.django_db
@override_settings(PUBLIC_BASE_DOMAIN="eclatstudio.com.br", ALLOWED_HOSTS=[".eclatstudio.com.br"])
def test_subdomain_desconhecido_retorna_404_claro():
    request = RequestFactory().get("/b/", HTTP_HOST="nao-existe.eclatstudio.com.br")
    response = PublicBookingTenantMiddleware(lambda req: HttpResponse("ok"))(request)
    assert response.status_code == 404
    assert b"Organiza\xc3\xa7\xc3\xa3o n\xc3\xa3o encontrada" in response.content


@pytest.mark.django_db
@override_settings(PUBLIC_BASE_DOMAIN="", ALLOWED_HOSTS=["testserver"])
def test_slug_explicito_da_rota_b_funciona_em_host_local():
    organization = OrganizationFactory(slug="salao-local")
    request = RequestFactory().get("/b/salao-local/", HTTP_HOST="testserver")
    response = PublicBookingTenantMiddleware(lambda req: HttpResponse(str(req.organization.pk)))(
        request
    )
    assert response.status_code == 200
    assert response.content.decode() == str(organization.pk)


@pytest.mark.django_db
@override_settings(PUBLIC_BASE_DOMAIN="", ALLOWED_HOSTS=["testserver"])
def test_api_publica_aceita_slug_explicito_enviado_pela_pagina_local():
    organization = OrganizationFactory(slug="salao-local")
    request = RequestFactory().get(
        "/api/v1/public/catalog/", HTTP_HOST="testserver", HTTP_X_TENANT_SLUG="salao-local"
    )
    response = PublicBookingTenantMiddleware(lambda req: HttpResponse(str(req.organization.pk)))(
        request
    )
    assert response.status_code == 200
    assert response.content.decode() == str(organization.pk)
