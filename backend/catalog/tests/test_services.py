"""Testes de serviços: CRUD, filtros, sanitização e isolamento (IDOR)."""

from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework import status

from catalog.factories import ServiceCategoryFactory, ServiceFactory

pytestmark = pytest.mark.django_db


def list_url():
    return reverse("service-list")


def detail_url(pk):
    return reverse("service-detail", kwargs={"pk": pk})


PAYLOAD = {
    "name": "Corte masculino",
    "description": "Corte + finalização",
    "duration_minutes": 45,
    "price": "80.00",
    "buffer_minutes": 10,
}


class TestCriarServico:
    def test_owner_cria_servico_com_categoria_do_salao(self, auth_client, organization):
        categoria = ServiceCategoryFactory(organization=organization)
        payload = {**PAYLOAD, "category": categoria.pk}
        response = auth_client.post(list_url(), payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["category_name"] == categoria.name
        assert data["duration_minutes"] == 45
        assert data["buffer_minutes"] == 10

    def test_categoria_de_outro_salao_rejeitada(
        self, auth_client, organization, other_organization
    ):
        """IDOR via FK: categoria do salão B não pode ser usada no salão A."""
        categoria_b = ServiceCategoryFactory(organization=other_organization)
        response = auth_client.post(
            list_url(), {**PAYLOAD, "category": categoria_b.pk}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert organization.catalog_service_set.count() == 0

    def test_professional_nao_cria_servico(self, professional_client, organization):
        categoria = ServiceCategoryFactory(organization=organization)
        response = professional_client.post(
            list_url(), {**PAYLOAD, "category": categoria.pk}, format="json"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_sanitizacao_da_descricao(self, auth_client, organization):
        """Descrição é texto simples: tags HTML são removidas (anti-XSS)."""
        categoria = ServiceCategoryFactory(organization=organization)
        payload = {
            **PAYLOAD,
            "category": categoria.pk,
            "description": "<script>alert(1)</script>Corte com <b>desconto</b>",
        }
        response = auth_client.post(list_url(), payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        service = organization.catalog_service_set.first()
        assert "<script>" not in service.description
        assert "alert(1)" in service.description  # conteúdo textual preservado
        assert "<b>" not in service.description


class TestListarServicos:
    def test_filtros_por_categoria_e_ativo(self, auth_client, organization):
        ativa = ServiceCategoryFactory(organization=organization, name="Cabelo")
        inativa = ServiceCategoryFactory(organization=organization, name="Barba")
        s1 = ServiceFactory(organization=organization, category=ativa, is_active=True)
        ServiceFactory(organization=organization, category=inativa, is_active=False)

        resposta_categoria = auth_client.get(list_url(), {"category": ativa.pk})
        assert resposta_categoria.json()["results"][0]["id"] == s1.pk

        resposta_ativos = auth_client.get(list_url(), {"is_active": "false"})
        assert resposta_ativos.json()["count"] == 1

    def test_isolamento_tenant(self, auth_client, organization, other_organization):
        ServiceFactory(organization=other_organization)
        assert auth_client.get(list_url()).json()["count"] == 0

    def test_sem_n_plus_1_na_listagem(self, auth_client, organization, django_assert_num_queries):
        categoria = ServiceCategoryFactory(organization=organization)
        for _ in range(5):
            ServiceFactory(organization=organization, category=categoria)
        # membership do tenant + COUNT + página com join da categoria (sem N+1)
        with django_assert_num_queries(3):
            response = auth_client.get(list_url())
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == 5


class TestEditarExcluirServico:
    def test_manager_edita(self, manager_client, organization):
        categoria = ServiceCategoryFactory(organization=organization)
        service = ServiceFactory(organization=organization, category=categoria)
        response = manager_client.patch(detail_url(service.pk), {"price": "999.90"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        service.refresh_from_db()
        assert service.price == Decimal("999.90")

    def test_professional_nao_edita(self, professional_client, organization):
        categoria = ServiceCategoryFactory(organization=organization)
        service = ServiceFactory(organization=organization, category=categoria)
        response = professional_client.patch(
            detail_url(service.pk), {"price": "1.00"}, format="json"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_idor_patch_de_outro_salao(self, professional_client, organization, other_organization):
        """IDOR: PATCH em serviço do salão B vira 404 (queryset escopado)."""
        service_b = ServiceFactory(organization=other_organization)
        response = professional_client.patch(
            detail_url(service_b.pk), {"price": "1.00"}, format="json"
        )
        assert response.status_code in (
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        )
        service_b.refresh_from_db()
        assert service_b.price != 1.00

    def test_excluir(self, auth_client, organization):
        categoria = ServiceCategoryFactory(organization=organization)
        service = ServiceFactory(organization=organization, category=categoria)
        assert auth_client.delete(detail_url(service.pk)).status_code == status.HTTP_204_NO_CONTENT
