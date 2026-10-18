"""Testes de categorias de serviço: CRUD, roles e isolamento de tenant (IDOR)."""

import pytest
from django.urls import reverse
from rest_framework import status

from catalog.factories import ServiceCategoryFactory, ServiceFactory

pytestmark = pytest.mark.django_db


def list_url():
    return reverse("service-category-list")


def detail_url(pk):
    return reverse("service-category-detail", kwargs={"pk": pk})


class TestCriarCategoria:
    def test_owner_cria_categoria(self, auth_client, organization):
        response = auth_client.post(list_url(), {"name": "Coloração", "order": 2}, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["name"] == "Coloração"
        categoria = organization.catalog_servicecategory_set.get()
        assert categoria.order == 2

    def test_manager_cria_categoria(self, manager_client, organization):
        response = manager_client.post(list_url(), {"name": "Cortes"}, format="json")
        assert response.status_code == status.HTTP_201_CREATED

    def test_professional_nao_cria_categoria(self, professional_client, organization):
        response = professional_client.post(list_url(), {"name": "X"}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert organization.catalog_servicecategory_set.count() == 0

    def test_anonimo_nao_acessa(self, api_client):
        assert api_client.get(list_url()).status_code == status.HTTP_401_UNAUTHORIZED

    def test_nome_duplicado_no_mesmo_salao_rejeitado(self, auth_client, organization):
        ServiceCategoryFactory(organization=organization, name="Barba")
        response = auth_client.post(list_url(), {"name": "Barba"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert organization.catalog_servicecategory_set.count() == 1

    def test_mesmo_nome_em_saloes_diferentes_e_permitido(
        self, auth_client, organization, other_organization
    ):
        ServiceCategoryFactory(organization=other_organization, name="Barba")
        response = auth_client.post(list_url(), {"name": "Barba"}, format="json")
        assert response.status_code == status.HTTP_201_CREATED


class TestListarCategorias:
    def test_todo_membro_do_salao_lista(self, professional_client, organization):
        ServiceCategoryFactory(organization=organization, name="Cabelo", order=2)
        response = professional_client.get(list_url())
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == 1

    def test_isolamento_tenant_nao_ve_outro_salao(
        self, auth_client, organization, other_organization
    ):
        """IDOR: categorias do salão B não aparecem para membros do salão A."""
        ServiceCategoryFactory(organization=other_organization, name="Do salão B")
        response = auth_client.get(list_url())
        assert response.json()["count"] == 0


class TestEditarExcluirCategoria:
    def test_owner_edita(self, auth_client, organization):
        categoria = ServiceCategoryFactory(organization=organization, name="Antigo")
        response = auth_client.patch(detail_url(categoria.pk), {"name": "Novo"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        categoria.refresh_from_db()
        assert categoria.name == "Novo"

    def test_professional_nao_edita(self, professional_client, organization):
        categoria = ServiceCategoryFactory(organization=organization)
        response = professional_client.patch(detail_url(categoria.pk), {"name": "X"}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_excluir_categoria_com_servico_rejeitado(self, auth_client, organization):
        categoria = ServiceCategoryFactory(organization=organization)
        ServiceFactory(organization=organization, category=categoria)
        response = auth_client.delete(detail_url(categoria.pk))
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["error"]["code"] == "category_in_use"

    def test_excluir_categoria_sem_servico_funciona(self, auth_client, organization):
        categoria = ServiceCategoryFactory(organization=organization)
        assert (
            auth_client.delete(detail_url(categoria.pk)).status_code == status.HTTP_204_NO_CONTENT
        )
