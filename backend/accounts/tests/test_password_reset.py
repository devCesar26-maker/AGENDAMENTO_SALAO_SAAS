"""Testes do fluxo de recuperação de senha (/auth/password/reset/...)."""

import pytest
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status

from accounts.factories import UserFactory

RESET_URL = reverse("auth-password-reset")
CONFIRM_URL = reverse("auth-password-reset-confirm")


@pytest.mark.django_db
class TestPasswordResetRequest:
    def test_email_existente_envia_link_para_o_console(self, api_client):
        UserFactory(email="reset@studio.com.br")
        response = api_client.post(
            RESET_URL, {"email": "reset@studio.com.br"}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert len(mail.outbox) == 1
        assert "resetar-senha" in mail.outbox[0].body

    def test_email_inexistente_resposta_identica_e_sem_email(self, api_client):
        response = api_client.post(
            RESET_URL, {"email": "fantasma@inexistente.com"}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert len(mail.outbox) == 0
        # Mensagem idêntica ao caso "email existe" (anti-enumeration):
        existente = api_client.post(RESET_URL, {"email": "ok@x.com"}, format="json")
        assert existente.json() == response.json()


@pytest.mark.django_db
class TestPasswordResetConfirm:
    def _criar_payload_valido(self, user):
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        return {"uidb64": uid, "token": token, "password": "NovaSenha#2026!"}

    def test_token_valido_redefine_senha_e_permite_login(self, api_client):
        user = UserFactory(email="reset@studio.com.br")
        payload = self._criar_payload_valido(user)

        response = api_client.post(CONFIRM_URL, payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        # Login com a nova senha:
        login = api_client.post(
            reverse("auth-login"),
            {"email": "reset@studio.com.br", "password": "NovaSenha#2026!"},
            format="json",
        )
        assert login.status_code == status.HTTP_200_OK
        # Senha antiga não funciona:
        old = api_client.post(
            reverse("auth-login"),
            {"email": "reset@studio.com.br", "password": "Senha#2026!"},
            format="json",
        )
        assert old.status_code == status.HTTP_401_UNAUTHORIZED

    def test_token_invalido_erro_generico(self, api_client):
        user = UserFactory()
        payload = self._criar_payload_valido(user)
        payload["token"] = "token-fabricado"

        response = api_client.post(CONFIRM_URL, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "inválido" in response.json()["error"]["detail"].lower()

    def test_uid_inexistente_erro_generico(self, api_client):
        response = api_client.post(
            CONFIRM_URL,
            {"uidb64": "AAAA", "token": "xxx", "password": "NovaSenha#2026!"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_senha_fraca_rejeitada_mantem_senha_antiga(self, api_client):
        user = UserFactory(email="reset@studio.com.br")
        payload = self._criar_payload_valido(user)
        payload["password"] = "12345678"

        response = api_client.post(CONFIRM_URL, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        user.refresh_from_db()
        assert user.check_password("Senha#2026!")
