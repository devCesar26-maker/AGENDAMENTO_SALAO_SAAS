"""Split de assinatura via Mercado Pago (marketplace): OAuth e marketplace_fee."""

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from billing import services
from billing.models import Plan, PlanTier
from organizations.models import Organization

pytestmark = pytest.mark.django_db


def test_checkout_sem_conta_conectada_nao_manda_marketplace_fee(monkeypatch, organization):
    captured = {}

    def fake_request(url, *, method="GET", payload=None, access_token=None):
        captured["payload"] = payload
        captured["access_token"] = access_token
        return {"id": "pre-1", "init_point": "https://mp/checkout"}

    monkeypatch.setattr("billing.services._mp_request", fake_request)
    result = services.create_checkout(organization=organization, tier=PlanTier.PLUS)

    assert result == {"checkout_url": "https://mp/checkout", "split_enabled": False}
    assert "marketplace_fee" not in captured["payload"]
    assert captured["access_token"] is None


def test_checkout_com_conta_conectada_aplica_comissao_ao_vendedor(monkeypatch, organization):
    organization.mercadopago_seller_id = "seller-1"
    organization.mercadopago_access_token = "SELLER-TOKEN"
    organization.platform_fee_percent = 15
    organization.save(
        update_fields=[
            "mercadopago_seller_id",
            "mercadopago_access_token",
            "platform_fee_percent",
            "updated_at",
        ]
    )
    captured = {}

    def fake_request(url, *, method="GET", payload=None, access_token=None):
        captured["payload"] = payload
        captured["access_token"] = access_token
        return {"id": "pre-2", "init_point": "https://mp/checkout"}

    monkeypatch.setattr("billing.services._mp_request", fake_request)
    result = services.create_checkout(organization=organization, tier=PlanTier.PLUS)

    assert result["split_enabled"] is True
    # O salão é o recebedor (token do vendedor) e a plataforma retém a comissão.
    assert captured["access_token"] == "SELLER-TOKEN"
    plan = Plan.objects.get(tier=PlanTier.PLUS)
    expected = round(plan.monthly_price_cents / 100 * 15 / 100, 2)
    assert captured["payload"]["marketplace_fee"] == expected


def test_checkout_comissao_nao_excede_o_valor_do_plano(monkeypatch, organization):
    organization.mercadopago_seller_id = "seller-1"
    organization.mercadopago_access_token = "SELLER-TOKEN"
    organization.platform_fee_percent = 100
    organization.save(
        update_fields=[
            "mercadopago_seller_id",
            "mercadopago_access_token",
            "platform_fee_percent",
            "updated_at",
        ]
    )
    captured = {}

    def fake_request(url, *, method="GET", payload=None, access_token=None):
        captured["payload"] = payload
        return {"id": "pre-3", "init_point": "https://mp/checkout"}

    monkeypatch.setattr("billing.services._mp_request", fake_request)
    services.create_checkout(organization=organization, tier=PlanTier.PREMIUM)

    plan = Plan.objects.get(tier=PlanTier.PREMIUM)
    assert captured["payload"]["marketplace_fee"] == plan.monthly_price_cents / 100


@override_settings(MP_CLIENT_ID="client-1", MP_OAUTH_REDIRECT_URI="https://app/cb")
def test_connect_retorna_url_de_autorizacao_para_owner(auth_client, organization):
    response = auth_client.get(reverse("billing-mercadopago-connect"))
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["connected"] is False
    assert body["authorization_url"].startswith("https://auth.mercadopago.com.br/authorization")
    assert "client_id=client-1" in body["authorization_url"]
    assert "state=" in body["authorization_url"]


def test_connect_exige_owner(professional_client):
    response = professional_client.get(reverse("billing-mercadopago-connect"))
    assert response.status_code == status.HTTP_403_FORBIDDEN


@override_settings(
    MP_CLIENT_ID="client-1",
    MP_CLIENT_SECRET="secret-1",
    MP_OAUTH_REDIRECT_URI="https://app/cb",
    MP_WEBHOOK_SECRET="hook-secret",
)
def test_callback_valida_state_e_persiste_tokens(monkeypatch, api_client, organization):
    url = services.build_mercadopago_authorization_url(organization=organization)
    state = url.split("state=")[1].split("&")[0]

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "access_token": "SELLER-TOKEN",
                "refresh_token": "REFRESH",
                "user_id": 987654,
                "expires_in": 15552000,
            }

    monkeypatch.setattr("billing.services.requests.post", lambda *args, **kwargs: FakeResponse())
    response = api_client.get(
        reverse("billing-mercadopago-callback"),
        {"slug": organization.slug, "code": "AUTH-CODE", "state": state},
    )
    assert response.status_code == status.HTTP_302_FOUND
    assert response["Location"].endswith("/app/plano?mp=conectado")
    organization.refresh_from_db()
    assert organization.mercadopago_seller_id == "987654"
    assert organization.mercadopago_access_token == "SELLER-TOKEN"
    assert organization.mercadopago_refresh_token == "REFRESH"
    assert organization.mercadopago_token_expires_at is not None
    assert organization.has_mercadopago_seller is True


@override_settings(MP_CLIENT_ID="client-1", MP_WEBHOOK_SECRET="hook-secret")
def test_callback_rejeita_state_adulterado(api_client, organization):
    response = api_client.get(
        reverse("billing-mercadopago-callback"),
        {"slug": organization.slug, "code": "AUTH-CODE", "state": "123.deadbeef"},
    )
    assert response.status_code == status.HTTP_302_FOUND
    assert response["Location"].endswith("/app/plano?mp=erro")
    organization.refresh_from_db()
    assert organization.mercadopago_access_token == ""


def test_oauth_state_isolado_por_slug(organization):
    timestamp = int(timezone.now().timestamp())
    valid = services._oauth_state(organization.slug, timestamp)
    assert services.verify_oauth_state(slug=organization.slug, state=valid) is True
    assert services.verify_oauth_state(slug="outro-salao", state=valid) is False


def test_disconnect_limpa_credenciais(auth_client, organization):
    organization.mercadopago_seller_id = "seller-1"
    organization.mercadopago_access_token = "SELLER-TOKEN"
    organization.mercadopago_refresh_token = "REFRESH"
    organization.mercadopago_connected_at = timezone.now()
    organization.save()

    response = auth_client.delete(reverse("billing-mercadopago-connect"))
    assert response.status_code == status.HTTP_204_NO_CONTENT
    organization.refresh_from_db()
    assert organization.mercadopago_seller_id == ""
    assert organization.mercadopago_access_token == ""
    assert organization.has_mercadopago_seller is False


def test_credenciais_nunca_vazam_no_serializer(auth_client, organization):
    organization.mercadopago_access_token = "SELLER-TOKEN"
    organization.mercadopago_refresh_token = "REFRESH"
    organization.mercadopago_seller_id = "seller-1"
    organization.save()

    response = auth_client.get(reverse("organization-detail", args=[organization.slug]))
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert "mercadopago_access_token" not in body
    assert "mercadopago_refresh_token" not in body
    assert body["platform_fee_percent"] == organization.platform_fee_percent


def test_comissao_padrao_vem_de_settings():
    assert Organization._meta.get_field("platform_fee_percent").default() == 10
