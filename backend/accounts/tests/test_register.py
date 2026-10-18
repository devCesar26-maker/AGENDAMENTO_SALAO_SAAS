"""Testes do POST /api/v1/auth/register/."""

import pytest
from django.urls import reverse
from rest_framework import status

from accounts.models import User
from billing.models import Subscription
from catalog.models import Service
from organizations.models import Membership, Organization

REGISTER_URL = reverse("auth-register")


@pytest.mark.django_db
class TestRegisterEndpoint:
    def test_cria_user_org_membership_owner_e_retorna_tokens(self, api_client):
        payload = {
            "email": "dono@studio.com.br",
            "password": "SenhaMuitoForte#2026!",
            "first_name": "Ana",
            "last_name": "Souza",
            "organization_name": "Studio Ana Beleza",
            "vertical": "SALAO",
            "organization_phone": "+55 11 99999-0000",
        }
        response = api_client.post(REGISTER_URL, payload, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert "access" in data and "refresh" in data
        assert data["user"]["email"] == "dono@studio.com.br"
        assert data["organization"]["slug"] == "studio-ana-beleza-ana"

        user = User.objects.get(email="dono@studio.com.br")
        organization = Organization.objects.get(slug="studio-ana-beleza-ana")
        assert organization.phone == "+55 11 99999-0000"
        membership = Membership.objects.get(user=user, organization=organization)
        assert membership.role == Membership.Role.OWNER
        assert membership.is_active is True
        # Salão nasce com assinatura FREE (signal existente):
        assert Subscription.objects.filter(organization=organization).exists()

    def test_slug_conflictivo_gera_sufixo_incremental(self, api_client):
        for i, nome in enumerate(("Studio Bello", "Studio Bello")):
            response = api_client.post(
                REGISTER_URL,
                {
                    "email": f"dono{i}@x.com",
                    "password": "SenhaForte#2026!",
                    "first_name": "A",
                    "organization_name": nome,
                    "vertical": "SALAO",
                },
                format="json",
            )
            assert response.status_code == status.HTTP_201_CREATED

        slugs = list(Organization.objects.all().values_list("slug", flat=True))
        assert slugs == ["studio-bello-a", "studio-bello-a-2"]

    @pytest.mark.parametrize(
        ("vertical", "expected"),
        [
            ("BARBEARIA", "Combo Corte + Barba"),
            ("SALAO", "Coloração"),
        ],
    )
    def test_registro_semeia_catalogo_da_vertical(self, api_client, vertical, expected):
        response = api_client.post(
            REGISTER_URL,
            {
                "email": f"{vertical.lower()}@studio.com.br",
                "password": "SenhaMuitoForte#2026!",
                "first_name": "Ana",
                "organization_name": "Studio Inicial",
                "vertical": vertical,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        organization = Organization.objects.get(
            pk=response.json()["organization"]["id"]
        )
        assert organization.vertical == vertical
        assert Service.objects.filter(organization=organization, name=expected).exists()
        assert organization.tema_cor == (
            "#2563EB" if vertical == "BARBEARIA" else "#8B5CF6"
        )

    def test_vertical_obrigatoria(self, api_client):
        response = api_client.post(
            REGISTER_URL,
            {
                "email": "semvertical@studio.com.br",
                "password": "SenhaMuitoForte#2026!",
                "first_name": "Ana",
                "organization_name": "Studio",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "vertical" in response.json()["error"]["fields"]

    def test_email_duplicado_nao_revela_existencia(self, api_client):
        payload = {
            "email": "dono@studio.com.br",
            "password": "SenhaMuitoForte#2026!",
            "first_name": "Ana",
            "organization_name": "Studio Ana",
            "vertical": "SALAO",
        }
        assert api_client.post(REGISTER_URL, payload, format="json").status_code == 201
        response = api_client.post(REGISTER_URL, payload, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        detail = str(response.json()["error"]["fields"]["email"][0])
        assert "já" not in detail.lower()  # nada sobre "já existe"/"em uso"
        assert User.objects.filter(email="dono@studio.com.br").count() == 1

    def test_senha_fraca_rejeitada(self, api_client):
        response = api_client.post(
            REGISTER_URL,
            {
                "email": "fraca@studio.com.br",
                "password": "12345678",
                "first_name": "Ana",
                "organization_name": "Studio Fraco",
                "vertical": "SALAO",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "password" in response.json()["error"]["fields"]

    def test_payload_nao_consegue_definir_role_ou_org_externa(self, api_client):
        response = api_client.post(
            REGISTER_URL,
            {
                "email": "hacker@studio.com.br",
                "password": "SenhaForte#2026!",
                "first_name": "H",
                "organization_name": "Studio X",
                "vertical": "SALAO",
                "role": "OWNER",
                "organization_id": 99999,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        membership = Membership.objects.get(user__email="hacker@studio.com.br")
        assert membership.role == Membership.Role.OWNER
        assert membership.organization_id != 99999
