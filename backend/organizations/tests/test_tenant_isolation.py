"""
Testes de isolamento multi-tenant (IDOR explícito).

Usuário do salão A tentando ler/criar/editar/deletar dados do salão B,
forçando o slug/payload da URL. Toda resposta deve ser 403/404 — nunca os
dados do outro tenant.
"""

import pytest
from django.urls import reverse
from rest_framework import status

from accounts.factories import UserFactory
from organizations.factories import (
    InvitationFactory,
    MembershipFactory,
    OrganizationFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant_a():
    org = OrganizationFactory(name="Studio A")
    owner_a = UserFactory(email="owner-a@x.com")
    MembershipFactory(organization=org, user=owner_a, role="OWNER")
    MembershipFactory(organization=org, role="PROFESSIONAL")
    InvitationFactory(organization=org, email="convite-a@x.com")
    return org, owner_a


@pytest.fixture
def tenant_b():
    org = OrganizationFactory(name="Studio B")
    owner_b = UserFactory(email="owner-b@x.com")
    MembershipFactory(organization=org, user=owner_b, role="OWNER")
    member_b = MembershipFactory(organization=org, role="PROFESSIONAL")
    invitation_b = InvitationFactory(organization=org, email="convite-b@x.com")
    return org, owner_b, member_b, invitation_b


@pytest.fixture
def client_do_dono_a(api_client, tenant_a):
    _, owner_a = tenant_a
    api_client.force_authenticate(user=owner_a)
    return api_client


class TestIsolamentoPorSlug:
    def test_dono_a_nao_ve_salao_b(self, client_do_dono_a, tenant_b):
        org_b = tenant_b[0]
        response = client_do_dono_a.get(reverse("organization-detail", kwargs={"slug": org_b.slug}))
        assert response.status_code in (
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        )
        assert "Studio B" not in str(response.content)

    def test_dono_a_nao_edita_salao_b(self, client_do_dono_a, tenant_b):
        org_b = tenant_b[0]
        response = client_do_dono_a.patch(
            reverse("organization-detail", kwargs={"slug": org_b.slug}),
            {"name": "Hacked Studio"},
            format="json",
        )
        assert response.status_code in (
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        )
        org_b.refresh_from_db()
        assert org_b.name == "Studio B"

    def test_dono_a_nao_cria_convite_em_salao_b(self, client_do_dono_a, tenant_b):
        org_b = tenant_b[0]
        response = client_do_dono_a.post(
            reverse("organization-invitations", kwargs={"slug": org_b.slug}),
            {"email": "invasor@x.com", "role": "OWNER"},
            format="json",
        )
        assert response.status_code in (
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        )
        assert org_b.invitations.count() == 1  # só o convite pré-existente de B

    def test_dono_a_nao_lista_convites_do_salao_b(self, client_do_dono_a, tenant_b):
        org_b = tenant_b[0]
        response = client_do_dono_a.get(
            reverse("organization-invitations", kwargs={"slug": org_b.slug})
        )
        assert response.status_code in (
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        )
        assert "convite-b@x.com" not in str(response.content)

    def test_dono_a_nao_lista_membros_do_salao_b(self, client_do_dono_a, tenant_b):
        org_b = tenant_b[0]
        response = client_do_dono_a.get(
            reverse("organization-members", kwargs={"slug": org_b.slug})
        )
        assert response.status_code in (
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        )
        assert "owner-b@x.com" not in str(response.content)

    def test_dono_a_nao_edita_membro_do_salao_b(self, client_do_dono_a, tenant_b):
        org_b, _, member_b, _ = tenant_b
        response = client_do_dono_a.patch(
            reverse(
                "organization-member-detail",
                kwargs={"slug": org_b.slug, "pk": member_b.id},
            ),
            {"role": "OWNer"},
            format="json",
        )
        assert response.status_code in (
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        )
        member_b.refresh_from_db()
        assert member_b.role == "PROFESSIONAL"


class TestIsolamentoPorPayload:
    def test_aceitar_convite_naoforca_role_propio(self, api_client, tenant_b):
        org_b, _, _, invitation_b = tenant_b
        response = api_client.post(
            reverse("invitation-accept", kwargs={"token": invitation_b.token}),
            {"role": "OWNer", "password": "SenhaNova#2026!"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        # role TEM que vir da Invitation, ignorando o payload:
        membership = org_b.memberships.filter(user__email=invitation_b.email).first()
        assert membership.role == invitation_b.role == "PROFESSIONAL"

    def test_token_de_convite_de_outra_org_so_aceita_uma_vez(self, api_client, tenant_b):
        org_b, _, _, invitation_b = tenant_b
        email = invitation_b.email
        api_client.post(
            reverse("invitation-accept", kwargs={"token": invitation_b.token}),
            {"password": "SenhaNova#2026!"},
            format="json",
        )
        reuso = api_client.post(
            reverse("invitation-accept", kwargs={"token": invitation_b.token}),
            {"password": "SenhaNova#2026!"},
            format="json",
        )
        assert reuso.status_code == status.HTTP_400_BAD_REQUEST
        assert org_b.memberships.filter(user__email=email).count() == 1
