"""Testes de convites: envio, listagem, aceite e expiração."""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from accounts.factories import UserFactory
from organizations.factories import InvitationFactory
from organizations.models import Invitation, Membership

pytestmark = pytest.mark.django_db


def inv_url(org):
    return reverse("organization-invitations", kwargs={"slug": org.slug})


def accept_url(token):
    return reverse("invitation-accept", kwargs={"token": token})


class TestCriarConvite:
    def test_owner_convida_e_email_vai_para_o_dev(self, auth_client, organization):
        response = auth_client.post(
            inv_url(organization),
            {"email": "NovoPro@STUDIO.com.br", "role": "PROFESSIONAL"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        invitation = Invitation.objects.get(
            organization=organization, email="novopro@studio.com.br"
        )
        assert invitation.accepted_at is None
        assert len(invitation.token) >= 32  # token_urlsafe seguro
        # E-mail com o link do convite (console/dev):
        assert len(mail.outbox) == 1
        assert invitation.token in mail.outbox[0].body
        # Convite expira em ~7 dias:
        assert invitation.expires_at > timezone.now() + timedelta(days=6)

    def test_email_normalizado_para_minusculas(self, auth_client, organization):
        auth_client.post(
            inv_url(organization),
            {"email": "  Xpto@STUDIO.COM.BR ", "role": "PROFESSIONAL"},
            format="json",
        )
        assert Invitation.objects.filter(
            organization=organization, email="xpto@studio.com.br"
        ).exists()

    def test_convite_duplicado_do_email_rejeitado(self, auth_client, organization):
        InvitationFactory(organization=organization, email="pendente@x.com")
        response = auth_client.post(
            inv_url(organization),
            {"email": "Pendente@x.com", "role": "MANAGER"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert organization.invitations.count() == 1

    def test_role_invalido_rejeitado(self, auth_client, organization):
        response = auth_client.post(
            inv_url(organization),
            {"email": "teste@x.com", "role": "SUPERUSER"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert organization.invitations.count() == 0


class TestListarConvites:
    def test_lista_somente_pendentes_nao_expirados(self, auth_client, organization):
        pendente = InvitationFactory(organization=organization, email="pendente@x.com")
        aceito = InvitationFactory(organization=organization, email="aceito@x.com")
        aceito.accepted_at = timezone.now()
        aceito.save(update_fields=["accepted_at", "updated_at"])
        InvitationFactory(
            organization=organization,
            email="expirado@x.com",
            expires_at=timezone.now() - timedelta(days=1),
        )

        response = auth_client.get(inv_url(organization))
        assert response.status_code == status.HTTP_200_OK
        emails = [item["email"] for item in response.json()["results"]]
        assert emails == ["pendente@x.com"]
        assert pendente.token in str(response.content)

    def test_pagina_when_paginacao_aplicada(self, auth_client, organization, settings):
        for i in range(25):
            InvitationFactory(organization=organization, email=f"lote-{i}@x.com")
        response = auth_client.get(inv_url(organization))
        data = response.json()
        assert data["count"] == 25
        assert len(data["results"]) == 20  # PAGE_SIZE padrão da DRF config


class TestAceitarConvite:
    def _payload(self, **kwargs):
        base = {
            "password": "SenhaNova#2026!",
            "first_name": "Carlos",
            "last_name": "Lima",
        }
        base.update(kwargs)
        return base

    def test_novo_usuario_created_com_role_do_convite(self, api_client, organization):
        invitation = InvitationFactory(
            organization=organization, email="novo@x.com", role="MANAGER"
        )
        response = api_client.post(
            accept_url(invitation.token),
            self._payload(role="OWNER"),  # payload NÃO define o role
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["role"] == "MANAGER"
        assert "access" in data and "refresh" in data

        user = get_user_model().objects.get(email="novo@x.com")
        membership = Membership.objects.get(user=user, organization=organization)
        assert membership.role == Membership.Role.MANAGER
        invitation.refresh_from_db()
        assert invitation.accepted_at is not None

    def test_usuario_existente_e_apenas_vinculado(self, api_client, organization):
        existing = UserFactory(email="seguidor@x.com")
        invitation = InvitationFactory(
            organization=organization, email="seguidor@x.com"
        )
        response = api_client.post(
            accept_url(invitation.token), {"password": "Outra#2026!"}, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        existing.refresh_from_db()
        assert existing.check_password("Senha#2026!")  # senha não foi alterada
        assert Membership.objects.filter(
            user=existing, organization=organization
        ).exists()

    def test_expirado_e_invalido_erro_identico(self, api_client):
        invitation_expirada = InvitationFactory(
            expires_at=timezone.now() - timedelta(days=1)
        )
        expired = api_client.post(
            accept_url(invitation_expirada.token), self._payload(), format="json"
        )
        invalido = api_client.post(
            accept_url("token-inexistente"), self._payload(), format="json"
        )

        assert expired.status_code == invalido.status_code
        assert expired.json() == invalido.json()

    def test_senha_obrigatoria_para_novo_usuario(self, api_client, organization):
        invitation = InvitationFactory(organization=organization, email="novinho@x.com")
        response = api_client.post(
            accept_url(invitation.token), {"first_name": "X"}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "password" in str(response.content).lower()
