"""Testes de GET/PATCH /api/v1/organizations/<slug>/."""

import pytest
from django.urls import reverse
from rest_framework import status

from accounts.factories import UserFactory
from organizations.factories import MembershipFactory, OrganizationFactory

pytestmark = pytest.mark.django_db


def org_url(org):
    return reverse("organization-detail", kwargs={"slug": org.slug})


def add_member(org, role):
    user = UserFactory()
    MembershipFactory(organization=org, user=user, role=role)
    return user


class TestOrganizationRetrieve:
    def test_owner_ve_dados_do_salao(self, api_client, organization):
        owner = organization._owner
        api_client.force_authenticate(user=owner)
        response = api_client.get(org_url(organization))

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == organization.name
        assert data["timezone"] == "America/Sao_Paulo"
        assert data["working_hours"] == {"mon": [["09:00", "18:00"]], "sun": []}

    def test_membro_profissional_ve_o_salao(self, api_client, organization):
        pro = add_member(organization, "PROFESSIONAL")
        api_client.force_authenticate(user=pro)
        assert api_client.get(org_url(organization)).status_code == status.HTTP_200_OK

    def test_nao_membro_recebe_403_sem_dados_e_slug_inexistente_404(self, api_client):
        outsider = UserFactory()
        org = OrganizationFactory()
        api_client.force_authenticate(user=outsider)

        # Não-membro: 403 e NUNHA dado do salão no corpo:
        response = api_client.get(org_url(org))
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert org.name not in str(response.content)
        # Slug inexistente: 404 (recurso não revelado):
        response = api_client.get(reverse("organization-detail", kwargs={"slug": "nao-existe-sl"}))
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestOrganizationUpdate:
    def test_owner_edita_dados_e_slug(self, api_client, organization):
        api_client.force_authenticate(user=organization._owner)
        response = api_client.patch(
            org_url(organization),
            {
                "phone": "+55 11 97777-7777",
                "slug": "novo-slug",
                "working_hours": {"mon": [["08:00", "20:00"]], "sun": []},
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        organization.refresh_from_db()
        assert organization.phone == "+55 11 97777-7777"
        assert organization.slug == "novo-slug"

    def test_manager_edita_mas_profissional_nao(self, api_client, organization):
        manager = add_member(organization, "MANAGER")
        api_client.force_authenticate(user=manager)
        assert (
            api_client.patch(
                org_url(organization), {"phone": "+55 11 90000-0000"}, format="json"
            ).status_code
            == 200
        )

        pro = add_member(organization, "PROFESSIONAL")
        api_client.force_authenticate(user=pro)
        assert (
            api_client.patch(
                org_url(organization), {"phone": "+55 11 88888-8888"}, format="json"
            ).status_code
            == 403
        )

    def test_slug_duplicado_rejeitado(self, api_client, organization):
        OrganizationFactory(name="Outro Studio")
        api_client.force_authenticate(user=organization._owner)
        response = api_client.patch(org_url(organization), {"slug": "outro-studio"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        organization.refresh_from_db()
        assert organization.slug != "outro-studio"

    def test_working_hours_invalido_rejeitado(self, api_client, organization):
        api_client.force_authenticate(user=organization._owner)
        response = api_client.patch(
            org_url(organization),
            {"working_hours": {"bad_day": [["09:00", "18:00"]]}},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
