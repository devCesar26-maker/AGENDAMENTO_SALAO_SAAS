"""Testes do GET /api/v1/me."""

import pytest
from django.urls import reverse
from rest_framework import status

from accounts.factories import UserFactory
from organizations.factories import MembershipFactory, OrganizationFactory

ME_URL = reverse("me")


@pytest.mark.django_db
class TestMeEndpoint:
    def test_exige_autenticacao(self, api_client):
        assert api_client.get(ME_URL).status_code == status.HTTP_401_UNAUTHORIZED

    def test_retorna_perfil_e_membros_do_salao(self, api_client):
        user = UserFactory(email="dono@me.com", first_name="Ana")
        org = OrganizationFactory(name="Meu Studio")
        my_membership = MembershipFactory(organization=org, user=user, role="OWNER")

        api_client.force_authenticate(user=user)
        response = api_client.get(ME_URL)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["email"] == "dono@me.com"
        assert len(data["memberships"]) == 1
        membership = data["memberships"][0]
        assert membership["id"] == my_membership.id
        assert membership["role"] == "OWNER"
        assert membership["organization"]["slug"] == org.slug

    def test_membros_inativos_nao_aparecem(self, api_client):
        user = UserFactory()
        MembershipFactory(user=user, is_active=False)

        api_client.force_authenticate(user=user)
        data = api_client.get(ME_URL).json()
        assert data["memberships"] == []

    def test_usuario_multi_tenant_lista_todos_os_saloes(self, api_client):
        user = UserFactory()
        MembershipFactory(user=user, role="OWNER")
        MembershipFactory(user=user, role="PROFESSIONAL")

        api_client.force_authenticate(user=user)
        data = api_client.get(ME_URL).json()
        assert {m["role"] for m in data["memberships"]} == {"OWNER", "PROFESSIONAL"}
