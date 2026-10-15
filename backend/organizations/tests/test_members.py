"""Testes de /api/v1/organizations/<slug>/members/ (lista e PATCH)."""

import pytest
from django.urls import reverse
from rest_framework import status

from accounts.factories import UserFactory
from organizations.factories import MembershipFactory, OrganizationFactory

pytestmark = pytest.mark.django_db


def members_url(org):
    return reverse("organization-members", kwargs={"slug": org.slug})


def member_url(org, member):
    return reverse("organization-member-detail", kwargs={"slug": org.slug, "pk": member.id})


def add_member(org, role="PROFESSIONAL"):
    user = UserFactory()
    return MembershipFactory(organization=org, user=user, role=role), user


class TestListarMembros:
    def test_lista_membros_com_paginacao_e_dados_do_user(self, api_client, organization):
        for _ in range(4):
            add_member(organization)
        api_client.force_authenticate(user=organization._owner)

        response = api_client.get(members_url(organization))

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["count"] == 5  # 1 owner + 4 profissionais
        resultado = data["results"][0]
        assert set(resultado.keys()) == {
            "id",
            "user",
            "organization",
            "role",
            "is_active",
            "created_at",
        }
        assert "email" in resultado["user"]

    def test_sem_n1_no_endpoint_de_membros(
        self, api_client, organization, django_assert_num_queries
    ):
        """Listagem de membros não deve disparar N+1 (User de cada Membership)."""
        for _ in range(10):
            add_member(organization)
        api_client.force_authenticate(user=organization._owner)

        with django_assert_num_queries(4):  # auth + blacklist + sessão + 1 query paginada
            response = api_client.get(members_url(organization))

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == 11

    def test_membros_de_outro_salao_nunca_sao_listados(self, api_client, organization):
        outro_org = OrganizationFactory(name="Outro Studio")
        MembershipFactory(organization=outro_org, role="PROFESSIONAL")
        add_member(organization)
        api_client.force_authenticate(user=organization._owner)

        response = api_client.get(members_url(organization))

        emails = [m["user"]["email"] for m in response.json()["results"]]
        assert response.json()["count"] == 2  # apenas owner + membro do próprio salão
        assert len(emails) == 2


class TestGerenciarMembros:
    def test_owner_altera_role(self, auth_client, organization):
        pro, _ = add_member(organization)
        response = auth_client.patch(
            member_url(organization, pro), {"role": "MANAGER"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        pro.refresh_from_db()
        assert pro.role == "MANAGER"

    def test_owner_desativa_membro_e_acesso_fail_closed(
        self, auth_client, api_client, organization
    ):
        pro, user = add_member(organization)
        response = auth_client.patch(
            member_url(organization, pro), {"is_active": False}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        pro.refresh_from_db()
        assert pro.is_active is False

        # O membro desativado perde o acesso (fail-closed):
        api_client.force_authenticate(user=user)
        assert api_client.get(members_url(organization)).status_code == status.HTTP_403_FORBIDDEN

    def test_nao_permitido_desativar_ultimo_owner(self, auth_client, organization):
        owner_membership = organization.memberships.get(user=organization._owner)
        response = auth_client.patch(
            member_url(organization, owner_membership), {"is_active": False}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        owner_membership.refresh_from_db()
        assert owner_membership.is_active is True

    def test_nao_permitido_rebaixar_ultimo_owner(self, auth_client, organization):
        owner_membership = organization.memberships.get(user=organization._owner)
        response = auth_client.patch(
            member_url(organization, owner_membership), {"role": "MANAGER"}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        owner_membership.refresh_from_db()
        assert owner_membership.role == "OWNER"

    def test_segundo_owner_permite_rebaixar_o_primeiro(self, auth_client, organization):
        add_member(organization, role="OWNER")
        owner_membership = organization.memberships.get(user=organization._owner)
        response = auth_client.patch(
            member_url(organization, owner_membership), {"role": "MANAGER"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        owner_membership.refresh_from_db()
        assert owner_membership.role == "MANAGER"

    def test_patch_membro_inexistente_404(self, auth_client, organization):
        response = auth_client.patch(
            member_url(organization, type("M", (), {"id": 999_999_999})),
            {"role": "MANAGER"},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
