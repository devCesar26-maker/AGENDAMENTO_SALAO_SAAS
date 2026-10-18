"""Testes de /auth/login/, /auth/refresh/ e /auth/logout/."""

import pytest
from django.conf import settings
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status

from accounts.factories import UserFactory
from accounts.services import register_failed_login
from organizations.factories import MembershipFactory, OrganizationFactory

SENHA = "Senha#2026!"

LOGIN_URL = reverse("auth-login")
REFRESH_URL = reverse("auth-refresh")
LOGOUT_URL = reverse("auth-logout")


@pytest.fixture
def user_com_membership(db):
    user = UserFactory(email="login@studio.com.br")
    MembershipFactory(organization=OrganizationFactory(), user=user, role="OWNER")
    return user


@pytest.fixture(autouse=True)
def limpa_cache_login():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
class TestLogin:
    def _payload(self, email="login@studio.com.br", senha=SENHA):
        return {"email": email, "password": senha}

    def test_login_valido_retorna_access_e_define_cookie_de_refresh(
        self, api_client, user_com_membership
    ):
        response = api_client.post(LOGIN_URL, self._payload(), format="json")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "access" in data and "refresh" not in data
        cookie = response.cookies[settings.REFRESH_TOKEN_COOKIE_NAME]
        assert cookie.value
        assert cookie["httponly"]
        assert cookie["samesite"] == "Lax"
        assert cookie["secure"] == ""
        assert cookie["path"] == settings.REFRESH_TOKEN_COOKIE_PATH
        assert data["user"]["email"] == "login@studio.com.br"
        assert data["user"]["organization"] is not None

    def test_email_ou_senha_incorretos_mensagem_generica(self, api_client, user_com_membership):
        wrong_password = api_client.post(
            LOGIN_URL, self._payload(senha="Errada#2026!"), format="json"
        )
        wrong_email = api_client.post(
            LOGIN_URL, self._payload(email="desconhecido@x.com"), format="json"
        )
        assert wrong_password.status_code == wrong_email.status_code == status.HTTP_401_UNAUTHORIZED
        detail_pw = wrong_password.json()["error"]["detail"]
        detail_em = wrong_email.json()["error"]["detail"]
        assert detail_pw == detail_em  # idêntico: não revela existência do e-mail
        assert "senha" in detail_pw.lower()

    def test_lockout_apos_limite_de_falhas(self, api_client, user_com_membership, settings):
        settings.LOGIN_MAX_FAILED_ATTEMPTS = 3
        settings.LOGIN_LOCKOUT_SECONDS = 900

        for _ in range(3):
            api_client.post(LOGIN_URL, self._payload(senha="Errada#2026!"), format="json")
        response = api_client.post(LOGIN_URL, self._payload(), format="json")  # senha correta

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert "tente novamente" in response.json()["error"]["detail"].lower()

    def test_lockout_expira_e_login_voltar_a_funcionar(
        self, api_client, user_com_membership, settings
    ):
        import time

        settings.LOGIN_MAX_FAILED_ATTEMPTS = 1
        settings.LOGIN_LOCKOUT_SECONDS = 1
        api_client.post(LOGIN_URL, self._payload(senha="Errada#2026!"), format="json")
        time.sleep(1.1)

        response = api_client.post(LOGIN_URL, self._payload(), format="json")
        assert response.status_code == status.HTTP_200_OK

    def test_sucesso_limpa_contador_de_falhas(self, api_client, user_com_membership, settings):
        settings.LOGIN_MAX_FAILED_ATTEMPTS = 2
        api_client.post(LOGIN_URL, self._payload(senha="Errada#2026!"), format="json")
        assert api_client.post(LOGIN_URL, self._payload(), format="json").status_code == 200
        # Counter foi limpo: 1 nova falha não trava imediatamente.
        api_client.post(LOGIN_URL, self._payload(senha="Errada#2026!"), format="json")
        assert api_client.post(LOGIN_URL, self._payload(), format="json").status_code == 200


@pytest.mark.django_db
class TestThrottleAuth:
    def test_auth_rate_throttle_bloqueia_por_ip(self, api_client, settings, db):
        """
        Simula esgotamento do limite 'auth' (por IP) pré-alimentando o histórico
        do throttle no cache — teste de integração real, sem hack de settings
        (DRF congela THROTTLE_RATES no import; override dinâmico não funciona).
        """
        import time

        from rest_framework.test import APIRequestFactory

        from core.api.throttling import AuthRateThrottle

        throttle = AuthRateThrottle()
        request = APIRequestFactory().post(LOGIN_URL)
        cache_key = throttle.cache_format % {
            "scope": throttle.scope,
            "ident": throttle.get_ident(request),
        }
        # Exatamente num_requests hits recentes (rate vigente em settings):
        rate = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["auth"]
        num_requests, _dur = throttle.parse_rate(rate)
        cache.set(cache_key, [time.time() - 0.1] * num_requests, timeout=None)

        response = api_client.post(
            LOGIN_URL, {"email": "t0@x.com", "password": "Errada#1234"}, format="json"
        )

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert "Retry-After" in response.headers


@pytest.mark.django_db
class TestRefreshAndLogout:
    def _login(self, api_client):
        response = api_client.post(
            LOGIN_URL,
            {"email": "login@studio.com.br", "password": SENHA},
            format="json",
        )
        tokens = response.json()
        tokens["refresh"] = response.cookies[settings.REFRESH_TOKEN_COOKIE_NAME].value
        return tokens

    def test_refresh_gera_novo_access_e_rotaciona(self, api_client, user_com_membership):
        tokens = self._login(api_client)
        response = api_client.post(REFRESH_URL, {}, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["access"] != tokens["access"]
        assert response.json()["user"]["email"] == "login@studio.com.br"
        assert response.cookies[settings.REFRESH_TOKEN_COOKIE_NAME].value != tokens["refresh"]

    def test_refresh_token_antigo_e_blacklistado_apos_rotacao(
        self, api_client, user_com_membership
    ):
        tokens = self._login(api_client)
        api_client.post(REFRESH_URL, {}, format="json")
        api_client.cookies[settings.REFRESH_TOKEN_COOKIE_NAME] = tokens["refresh"]
        reuso = api_client.post(REFRESH_URL, {}, format="json")

        assert reuso.status_code == status.HTTP_401_UNAUTHORIZED

    def test_logout_blacklista_refresh_token(self, api_client, user_com_membership):
        tokens = self._login(api_client)
        api_client.force_authenticate(user=user_com_membership)
        response = api_client.post(LOGOUT_URL, {}, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.cookies[settings.REFRESH_TOKEN_COOKIE_NAME]["max-age"] == 0
        reuso = api_client.post(REFRESH_URL, {"refresh": tokens["refresh"]}, format="json")
        assert reuso.status_code == status.HTTP_401_UNAUTHORIZED

    def test_logout_com_token_invalido_retorna_400(self, api_client, user_com_membership):
        api_client.force_authenticate(user=user_com_membership)
        response = api_client.post(LOGOUT_URL, {"refresh": "token-falso-123"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_logout_exige_autenticacao(self, api_client):
        assert (
            api_client.post(LOGOUT_URL, {"refresh": "qualquer"}, format="json").status_code == 401
        )


@pytest.mark.django_db
class TestRegisterFailedLoginCounter:
    def test_register_failed_login_acumula_e_bloqueia(self, settings):
        settings.LOGIN_MAX_FAILED_ATTEMPTS = 2
        register_failed_login("a@x.com")
        register_failed_login("a@x.com")
        assert register_failed_login("a@x.com") is None
