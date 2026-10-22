"""Cobertura do webhook de saída: CRUD, assinatura, idempotência e falhas."""

import hmac
import json
from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
import requests
from django.urls import reverse

from core.models import IdempotencyKey
from customers.models import Customer
from organizations.models import WebhookConfig
from organizations.tasks import dispatch_webhook_event
from scheduling.models import Appointment
from scheduling.services import change_appointment_status, create_appointment
from scheduling.tests.test_public_booking import make_public_schedule

pytestmark = pytest.mark.django_db


def create_webhook(organization, *, events, url="https://destinatario.test/hook", **kwargs):
    return WebhookConfig.objects.create(organization=organization, url=url, events=events, **kwargs)


def scheduled_appointment(organization):
    _, service, professional = make_public_schedule(organization)
    customer = Customer.objects.create(
        organization=organization, name="Cliente webhook", phone="11933002200"
    )
    return create_appointment(
        organization=organization,
        customer=customer,
        items=[{"service": service, "professional": professional, "order": 0}],
        desired_start=datetime(2026, 10, 19, 9, 0, tzinfo=ZoneInfo("America/Sao_Paulo")),
        membership=None,
    )


def post_response(status_code=200):
    return MagicMock(status_code=status_code)


# ── CRUD autenticado (OWNER/MANAGER) ─────────────────────────────────────


def test_criacao_devolve_secret_uma_vez_e_listagem_nao_exibe(auth_client, organization):
    url = reverse("organization-webhooks", kwargs={"slug": organization.slug})
    response = auth_client.post(
        url,
        {
            "url": "https://destinatario.test/hook",
            "events": ["appointment.created", "appointment.created"],
        },
        format="json",
    )
    assert response.status_code == 201, response.json()
    body = response.json()
    assert "secret" in body and len(body["secret"]) == 64
    assert body["events"] == ["appointment.created"], "eventos devem ser deduplicados"

    listing = auth_client.get(url)
    assert listing.status_code == 200
    items = listing.json()["results"] if isinstance(listing.json(), dict) else listing.json()
    assert len(items) == 1
    assert "secret" not in items[0]
    assert "last_failure_at" in items[0]


def test_profissional_nao_gerencia_webhooks(professional_client, organization):
    url = reverse("organization-webhooks", kwargs={"slug": organization.slug})
    response = professional_client.post(
        url,
        {"url": "https://destinatario.test/hook", "events": ["appointment.created"]},
        format="json",
    )
    assert response.status_code == 403


def test_url_sem_https_e_rejeitada(auth_client, organization):
    url = reverse("organization-webhooks", kwargs={"slug": organization.slug})
    response = auth_client.post(
        url,
        {"url": "http://destinatario.test/hook", "events": ["appointment.created"]},
        format="json",
    )
    assert response.status_code == 400
    assert "HTTPS" in str(response.json())


def test_evento_desconhecido_e_rejeitado(auth_client, organization):
    url = reverse("organization-webhooks", kwargs={"slug": organization.slug})
    response = auth_client.post(
        url,
        {"url": "https://destinatario.test/hook", "events": ["servico.inexistente"]},
        format="json",
    )
    assert response.status_code == 400


def test_update_e_delete_do_webhook_da_propria_organizacao(auth_client, organization):
    webhook = create_webhook(organization, events=["appointment.created"])
    url = reverse(
        "organization-webhook-detail", kwargs={"slug": organization.slug, "pk": webhook.pk}
    )
    patched = auth_client.patch(
        url, {"url": "https://novo.test/hook", "events": ["appointment.canceled"]}, format="json"
    )
    assert patched.status_code == 200, patched.json()
    webhook.refresh_from_db()
    assert webhook.url == "https://novo.test/hook"
    assert webhook.events == ["appointment.canceled"]

    deleted = auth_client.delete(url)
    assert deleted.status_code == 204
    assert not WebhookConfig.objects.filter(pk=webhook.pk).exists()


def test_isolamento_de_tenant_no_crud(auth_client, organization, other_organization):
    webhook_b = create_webhook(other_organization, events=["appointment.created"])
    # A organização B tem slug próprio; o OWNER de A não vê os webhooks de B.
    listing = auth_client.get(
        reverse("organization-webhooks", kwargs={"slug": other_organization.slug})
    )
    assert listing.status_code == 403

    patched = auth_client.patch(
        reverse(
            "organization-webhook-detail",
            kwargs={"slug": organization.slug, "pk": webhook_b.pk},
        ),
        {"events": ["appointment.canceled"]},
        format="json",
    )
    assert patched.status_code == 404
    webhook_b.refresh_from_db()
    assert webhook_b.events == ["appointment.created"]


# ── Disparo com assinatura HMAC ──────────────────────────────────────────


def _signature_of(secret, headers, body):
    ts_part, version_part = headers["X-ECALT-Signature"].split(",", 1)
    assert ts_part.startswith("t=")
    assert version_part.startswith("v1=")
    expected = hmac.new(secret.encode(), f"{ts_part[2:]}.".encode() + body, "sha256").hexdigest()
    assert headers["X-ECALT-Signature"] == f"t={ts_part[2:]},v1={expected}"
    return expected


def test_dispara_no_evento_assinado_com_assinatura_correta(
    auth_client, organization, django_capture_on_commit_callbacks
):
    webhook = create_webhook(organization, events=["appointment.created"])
    with patch("organizations.tasks.requests.post") as fake_post:
        fake_post.return_value = post_response(200)
        with django_capture_on_commit_callbacks(execute=True):
            appointment = scheduled_appointment(organization)

    # A criação do agendamento dispara o webhook via on_commit (Celery eager).
    assert IdempotencyKey.objects.filter(
        context="webhook_appointment.created", key=f"{webhook.pk}:{appointment.pk}"
    ).exists()
    assert fake_post.call_count >= 1
    body_bytes, headers = _extract_call(fake_post)
    _signature_of(webhook.secret, headers, body_bytes)
    payload = json.loads(body_bytes)
    assert payload["event"] == "appointment.created"
    assert payload["organization"] == {"id": organization.pk, "slug": organization.slug}
    assert payload["appointment"]["status"] == Appointment.Status.SCHEDULED
    assert payload["appointment"]["id"] == appointment.pk
    webhook.refresh_from_db()
    assert webhook.last_failure_at is None


def _extract_call(fake_post):
    call = fake_post.call_args
    body_bytes = call.kwargs["data"]
    headers = call.kwargs["headers"]
    return body_bytes, headers


def test_retry_nao_duplica_envio(auth_client, organization):
    create_webhook(organization, events=["appointment.created"])
    appointment = scheduled_appointment(organization)

    with patch("organizations.tasks.requests.post") as fake_post:
        fake_post.return_value = post_response(200)
        first = dispatch_webhook_event(
            "appointment.created",
            organization.pk,
            appointment.pk,
            occurred_at=appointment.created_at.isoformat(),
        )
        second = dispatch_webhook_event(
            "appointment.created",
            organization.pk,
            appointment.pk,
            occurred_at=appointment.created_at.isoformat(),
        )
    assert first == 1
    assert second == 0
    assert fake_post.call_count == 1


def test_evento_nao_assinado_nao_dispara(auth_client, organization):
    webhook = create_webhook(organization, events=["appointment.created"])
    appointment = scheduled_appointment(organization)

    with patch("organizations.tasks.requests.post") as fake_post:
        change_appointment_status(appointment, Appointment.Status.CANCELED, actor=None)
        dispatch_webhook_event(
            "appointment.canceled",
            organization.pk,
            appointment.pk,
            occurred_at=appointment.created_at.isoformat(),
        )
    assert fake_post.call_count == 0
    webhook.refresh_from_db()
    assert webhook.last_failure_at is None


def test_cancelamento_e_conclusao_disparam_eventos_corretos(organization):
    create_webhook(organization, events=["appointment.canceled", "appointment.completed"])

    with patch("organizations.tasks.requests.post") as fake_post:
        fake_post.return_value = post_response(200)
        appointment = scheduled_appointment(organization)
        # 'created' não está assinado neste webhook: nenhum disparo no evento de criação.
        delivered_created = dispatch_webhook_event(
            "appointment.created",
            organization.pk,
            appointment.pk,
            occurred_at=appointment.created_at.isoformat(),
        )
        assert delivered_created == 0
        change_appointment_status(appointment, Appointment.Status.COMPLETED, actor=None)
        dispatch_webhook_event(
            "appointment.completed",
            organization.pk,
            appointment.pk,
            occurred_at=appointment.created_at.isoformat(),
        )
        change_appointment_status(appointment, Appointment.Status.CANCELED, actor=None)
        delivered_canceled = dispatch_webhook_event(
            "appointment.canceled",
            organization.pk,
            appointment.pk,
            occurred_at=appointment.created_at.isoformat(),
        )
    events = [call.kwargs["headers"]["X-ECALT-Event"] for call in fake_post.call_args_list]
    assert len(events) == 2
    assert events[0] == "appointment.completed"
    assert events[1] == "appointment.canceled"
    assert delivered_canceled == 1


def test_falha_de_entrega_registra_ultimo_erro_sem_quebra(organization):
    ok_webhook = create_webhook(organization, events=["appointment.created"])
    broken_webhook = create_webhook(
        organization,
        events=["appointment.created"],
        url="https://quebrado.test/hook",
    )
    appointment = scheduled_appointment(organization)

    def flaky_post(url, **kwargs):
        if url.startswith("https://quebrado.test"):
            raise requests.ConnectionError("timeout simulado")
        return post_response(200)

    with patch("organizations.tasks.requests.post", side_effect=flaky_post):
        # Não pode derrubar a task nem travar o webhook saudável.
        result = dispatch_webhook_event(
            "appointment.created",
            organization.pk,
            appointment.pk,
            occurred_at=appointment.created_at.isoformat(),
        )
    assert result == 1

    ok_webhook.refresh_from_db()
    broken_webhook.refresh_from_db()
    assert ok_webhook.last_failure_at is None
    assert broken_webhook.last_failure_at is not None
    assert "ConnectionError" in broken_webhook.last_failure_detail


def test_resposta_5xx_do_destinatario_registra_falha(organization):
    webhook = create_webhook(organization, events=["appointment.created"])
    appointment = scheduled_appointment(organization)

    with patch("organizations.tasks.requests.post") as fake_post:
        fake_post.return_value = post_response(500)
        dispatch_webhook_event(
            "appointment.created",
            organization.pk,
            appointment.pk,
            occurred_at=appointment.created_at.isoformat(),
        )
    webhook.refresh_from_db()
    assert webhook.last_failure_at is not None
    assert "HTTP 500" in webhook.last_failure_detail


def test_isolamento_de_tenant_no_disparo(organization, other_organization):
    webhook_b = create_webhook(other_organization, events=["appointment.created"])
    appointment = scheduled_appointment(organization)

    with patch("organizations.tasks.requests.post") as fake_post:
        delivered = dispatch_webhook_event(
            "appointment.created",
            organization.pk,
            appointment.pk,
            occurred_at=appointment.created_at.isoformat(),
        )
    assert delivered == 0
    assert fake_post.call_count == 0
    webhook_b.refresh_from_db()
    assert webhook_b.last_failure_at is None
