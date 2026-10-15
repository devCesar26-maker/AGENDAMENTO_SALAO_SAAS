"""Testes de escalonamento de privilégio dentro do próprio salão."""

from uuid import uuid4

import pytest
from django.urls import reverse
from rest_framework import status

from accounts.factories import UserFactory
from organizations.factories import MembershipFactory, OrganizationFactory

pytestmark = pytest.mark.django_db


def _org_com_membro_do_role(role, **kwargs):
    org = OrganizationFactory(name=f"Studio {role} {uuid4().hex[:6]}")
    user = UserFactory()
    MembershipFactory(organization=org, user=user, role=role)
    return org, user


def _add_membro(org, role):
    """Cria membro e retorna (membership, user) para evitar confusão de ids."""
    user = UserFactory()
    membership = MembershipFactory(organization=org, user=user, role=role)
    return membership, user


class TestProfessionalEscalation:
    def test_professional_nao_convida(self, api_client):
        org, pro = _org_com_membro_do_role("PROFESSIONAL")
        api_client.force_authenticate(user=pro)
        response = api_client.post(
            reverse("organization-invitations", kwargs={"slug": org.slug}),
            {"email": "alguem@x.com", "role": "MANAGER"},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert org.invitations.count() == 0

    def test_professional_nao_lista_convites(self, api_client):
        org, pro = _org_com_membro_do_role("PROFESSIONAL")
        api_client.force_authenticate(user=pro)
        response = api_client.get(reverse("organization-invitations", kwargs={"slug": org.slug}))
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_professional_nao_organizacao_edita(self, api_client):
        org, pro = _org_com_membro_do_role("PROFESSIONAL")
        api_client.force_authenticate(user=pro)
        response = api_client.patch(
            reverse("organization-detail", kwargs={"slug": org.slug}), {"phone": "x"}, format="json"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_professional_nao_altera_membros(self, api_client):
        org, pro = _org_com_membro_do_role("PROFESSIONAL")
        target, _ = _add_membro(org, "PROFESSIONAL")
        api_client.force_authenticate(user=pro)
        response = api_client.patch(
            reverse("organization-member-detail", kwargs={"slug": org.slug, "pk": target.id}),
            {"role": "MANAGER"},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        target.refresh_from_db()
        assert target.role == "PROFESSIONAL"

    def test_professional_vendo_membros_nao_ve_outros_saloes(self, api_client):
        org, pro = _org_com_membro_do_role("PROFESSIONAL")
        outro_org = OrganizationFactory(name=f"Outro Studio {uuid4().hex[:6]}")
        MembershipFactory(organization=outro_org, role="PROFESSIONAL")
        api_client.force_authenticate(user=pro)
        response = api_client.get(reverse("organization-members", kwargs={"slug": org.slug}))
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["count"] == 1  # apenas o pro do próprio salão


class TestManagerLimits:
    def test_manager_nao_gerencia_membros(self, api_client):
        org, manager = _org_com_membro_do_role("MANAGER")
        target, _ = _add_membro(org, "PROFESSIONAL")
        api_client.force_authenticate(user=manager)
        response = api_client.patch(
            reverse("organization-member-detail", kwargs={"slug": org.slug, "pk": target.id}),
            {"is_active": False},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_manager_convida_gerentes_e_profissionais(self, api_client):
        org, manager = _org_com_membro_do_role("MANAGER")
        api_client.force_authenticate(user=manager)
        for role in ("MANAGER", "PROFESSIONAL"):
            response = api_client.post(
                reverse("organization-invitations", kwargs={"slug": org.slug}),
                {"email": f"novo-{role}@x.com", "role": role},
                format="json",
            )
            assert response.status_code == status.HTTP_201_CREATED

    def test_owner_keeps_access_mesmo_apos_demover_outro(self, api_client):
        org, owner = _org_com_membro_do_role("OWNER")
        manager, _unused_user = _add_membro(org, "MANAGER")
        api_client.force_authenticate(user=owner)
        response = api_client.patch(
            reverse("organization-member-detail", kwargs={"slug": org.slug, "pk": manager.id}),
            {"role": "PROFESSIONAL"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
