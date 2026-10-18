"""Testes de vínculos serviço ↔ profissional: link/unlink, overrides e 403s."""

import pytest
from django.urls import reverse
from rest_framework import status

from catalog.factories import (
    ProfessionalFactory,
    ServiceCategoryFactory,
    ServiceFactory,
)
from catalog.models import ProfessionalService
from catalog.services import link_service_to_professional

pytestmark = pytest.mark.django_db


def link_list_url(professional_pk):
    return reverse("professional-service-list", kwargs={"professional_id": professional_pk})


def link_detail_url(pk):
    return reverse("professional-service-detail", kwargs={"pk": pk})


@pytest.fixture
def servicos(organization):
    categoria = ServiceCategoryFactory(organization=organization)
    return [ServiceFactory(organization=organization, category=categoria) for _ in range(2)]


class TestVincular:
    def test_owner_vincula_com_overrides(self, auth_client, organization, professional, servicos):
        payload = {
            "service": servicos[0].pk,
            "price_override": "150.00",
            "duration_override": 30,
            "commission_percentage": 40.50,
        }
        response = auth_client.post(link_list_url(professional.pk), payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["service"] == servicos[0].pk
        assert data["price_override"] == "150.00"
        assert data["commission_percentage"] == "40.50"

    def test_vinculo_duplicado_rejeitado(self, auth_client, professional, servicos):
        link_service_to_professional(professional=professional, service=servicos[0])
        response = auth_client.post(
            link_list_url(professional.pk), {"service": servicos[0].pk}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_servico_de_outro_salao_rejeitado(self, auth_client, professional, other_organization):
        categoria_b = ServiceCategoryFactory(organization=other_organization)
        service_b = ServiceFactory(organization=other_organization, category=categoria_b)
        response = auth_client.post(
            link_list_url(professional.pk), {"service": service_b.pk}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert professional.service_links.count() == 0

    def test_professional_vincula_no_proprio_perfil(
        self, professional_client, professional, servicos
    ):
        response = professional_client.post(
            link_list_url(professional.pk), {"service": servicos[0].pk}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_professional_nao_vincula_em_outro(
        self, professional, organization, professional_client, servicos
    ):
        """Regra da Fase 2: PROFESSIONAL só mexe nos PRÓPRIOS registros."""
        outro = ProfessionalFactory(organization=organization, name="Colega")
        response = professional_client.post(
            link_list_url(outro.pk), {"service": servicos[0].pk}, format="json"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert outro.service_links.count() == 0


class TestEditarDesvincular:
    def test_owner_ajusta_overrides(self, auth_client, professional, servicos):
        link = link_service_to_professional(professional=professional, service=servicos[0])
        response = auth_client.patch(
            link_detail_url(link.pk), {"price_override": "99.00"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["price_override"] == "99.00"

    def test_professional_ajusta_o_proprio(self, professional_client, professional, servicos):
        link = link_service_to_professional(professional=professional, service=servicos[0])
        response = professional_client.patch(
            link_detail_url(link.pk), {"commission_percentage": 10}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_professional_nao_ajusta_de_outro(
        self, professional, organization, professional_client, servicos
    ):
        outro = ProfessionalFactory(organization=organization)
        link_outro = link_service_to_professional(professional=outro, service=servicos[0])
        response = professional_client.patch(
            link_detail_url(link_outro.pk), {"price_override": "1.00"}, format="json"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_professional_desvincula_o_proprio(self, professional_client, professional, servicos):
        link = link_service_to_professional(professional=professional, service=servicos[0])
        response = professional_client.delete(link_detail_url(link.pk))
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert professional.service_links.count() == 0

    def test_professional_nao_desvincula_de_outro(
        self, professional, organization, professional_client, servicos
    ):
        outro = ProfessionalFactory(organization=organization)
        link_outro = link_service_to_professional(professional=outro, service=servicos[0])
        response = professional_client.delete(link_detail_url(link_outro.pk))
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert ProfessionalService.objects.filter(pk=link_outro.pk).exists()
