"""Testes de profissionais: CRUD, vinculação de conta e permissões por role."""

import pytest
from django.urls import reverse
from rest_framework import status

from catalog.factories import (
    ProfessionalFactory,
    ServiceCategoryFactory,
    ServiceFactory,
)

pytestmark = pytest.mark.django_db


def list_url():
    return reverse("professional-list")


def detail_url(pk):
    return reverse("professional-detail", kwargs={"pk": pk})


@pytest.fixture
def categoria(organization):
    return ServiceCategoryFactory(organization=organization)


@pytest.fixture
def servico(organization, categoria):
    return ServiceFactory(organization=organization, category=categoria)


class TestCriarProfessional:
    def test_owner_cria_com_usuario_membro_ativo(
        self, auth_client, organization, professional_user
    ):
        payload = {"name": "João Cabeleireiro", "user": professional_user.pk}
        response = auth_client.post(list_url(), payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["user"]["email"] == professional_user.email

    def test_usuario_fora_do_salao_rejeitado(self, auth_client, organization, other_organization):
        """Anti-escalonamento: não pode vincular usuário de outro salão."""
        payload = {"name": "X", "user": other_organization._professional.user.pk}
        response = auth_client.post(list_url(), payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_mesmo_usuario_duas_vezes_rejeitado(
        self, auth_client, organization, professional_user, professional
    ):
        payload = {"name": "Duplicado", "user": professional_user.pk}
        response = auth_client.post(list_url(), payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_professional_nao_cria_outro_professional(self, professional_client):
        response = professional_client.post(list_url(), {"name": "X"}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_sem_usuario_e_opcional(self, auth_client, organization):
        response = auth_client.post(list_url(), {"name": "Freelancer"}, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["user"] is None


class TestListarProfessional:
    def test_todo_membro_lista(self, professional_client, organization, professional, servico):
        """GET inclui service_links sem N+1."""
        from catalog.services import link_service_to_professional

        link_service_to_professional(
            professional=professional, service=servico, commission_percentage=50
        )
        response = professional_client.get(list_url())
        assert response.status_code == status.HTTP_200_OK
        data = response.json()["results"][0]
        assert data["service_links"][0]["service"] == servico.pk
        assert data["service_links"][0]["commission_percentage"] == "50.00"

    def test_isolamento_tenant(self, auth_client, organization, other_organization):
        ProfessionalFactory(organization=other_organization)
        assert auth_client.get(list_url()).json()["count"] == 0

    def test_sem_n_plus_1_na_listagem(
        self, auth_client, organization, professional, django_assert_num_queries
    ):
        from catalog.services import link_service_to_professional

        servicos = []
        for _ in range(3):
            servico = ServiceFactory(organization=organization)
            servicos.append(servico)
            link_service_to_professional(professional=professional, service=servico)
        # membership + COUNT + página + prefetch de service_links/service/categoria
        with django_assert_num_queries(4):
            response = auth_client.get(list_url())
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == 1


class TestEditarProfessional:
    def test_manager_edita_qualquer(self, manager_client, organization, professional):
        response = manager_client.patch(
            detail_url(professional.pk), {"name": "Novo nome"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        professional.refresh_from_db()
        assert professional.name == "Novo nome"

    def test_professional_edita_proprios_dados_basicos(self, professional_client, professional):
        response = professional_client.patch(
            detail_url(professional.pk), {"name": "Eu mesmo"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        professional.refresh_from_db()
        assert professional.name == "Eu mesmo"

    def test_professional_nao_edita_active_nem_user(self, professional_client, professional):
        """Um PROFESSIONAL não pode desativar a si mesmo nem trocar usuário."""
        response_active = professional_client.patch(
            detail_url(professional.pk), {"is_active": False}, format="json"
        )
        assert response_active.status_code == status.HTTP_200_OK
        professional.refresh_from_db()
        assert professional.is_active is True

        response_user = professional_client.patch(
            detail_url(professional.pk), {"user": None}, format="json"
        )
        assert response_user.status_code == status.HTTP_200_OK
        professional.refresh_from_db()
        assert professional.user is not None  # `user` é read-only para PROFESSIONAL

    def test_professional_nao_edita_outro_do_mesmo_salao(
        self, professional, organization, professional_client
    ):
        """Regra explícita da Fase 2: 403 ao mexer no perfil de outro profissional."""
        outro = ProfessionalFactory(organization=organization, name="Colega")
        response = professional_client.patch(
            detail_url(outro.pk), {"name": "Hacked"}, format="json"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        outro.refresh_from_db()
        assert outro.name == "Colega"

    def test_manager_desativa_professional(self, manager_client, professional):
        response = manager_client.patch(
            detail_url(professional.pk), {"is_active": False}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        professional.refresh_from_db()
        assert professional.is_active is False


class TestExcluirProfessional:
    def test_owner_exclui(self, auth_client, professional):
        assert (
            auth_client.delete(detail_url(professional.pk)).status_code
            == status.HTTP_204_NO_CONTENT
        )

    def test_professional_nao_exclui_nem_o_proprio(self, professional_client, professional):
        assert (
            professional_client.delete(detail_url(professional.pk)).status_code
            == status.HTTP_403_FORBIDDEN
        )
