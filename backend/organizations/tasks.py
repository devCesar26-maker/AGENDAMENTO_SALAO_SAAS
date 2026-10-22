"""Tarefas assíncronas de webhook de saída (nunca bloqueiam o request HTTP)."""

import hmac
import json
import logging
import time

import requests
from celery import shared_task
from django.utils import timezone

from core.idempotency import claim_side_effect, complete_side_effect, release_side_effects
from organizations.models import WebhookConfig

logger = logging.getLogger("ecalt")

WEBHOOK_TIMEOUT_SECONDS = 10
SIGNATURE_HEADER = "X-ECALT-Signature"
TIMESTAMP_HEADER = "X-ECALT-Timestamp"
EVENT_HEADER = "X-ECALT-Event"
DELIVERY_HEADER = "X-ECALT-Delivery"


class WebhookDeliveryError(Exception):
    """Resposta do endpoint não confirmou o recebimento (status fora de 2xx)."""


def _delivery_id(config: WebhookConfig) -> str:
    """Identificador de entrega (não revela o secret)."""
    import hashlib

    return hashlib.sha256(b"ecalt-webhook-delivery:" + config.secret.encode()).hexdigest()[:32]


def _appointment_webhook_payload(event: str, appointment, occurred_at) -> dict:
    """Payload mínimo e estável do evento; sem dados sensíveis do cliente."""
    organization = appointment.organization
    items = [
        {
            "service": item.service_id,
            "service_name": item.service.name,
            "professional": item.professional_id,
            "professional_name": item.professional.name,
            "start_at": item.start_at.isoformat(),
            "end_at": item.end_at.isoformat(),
        }
        for item in appointment.items.order_by("order")
    ]
    return {
        "event": event,
        "occurred_at": (occurred_at if isinstance(occurred_at, str) else occurred_at.isoformat()),
        "organization": {"id": organization.pk, "slug": organization.slug},
        "appointment": {
            "id": appointment.pk,
            "status": appointment.status,
            "customer_id": appointment.customer_id,
            "items": items,
        },
    }


def _deliver(config: WebhookConfig, event: str, payload: dict) -> bool:
    """POST assinado com HMAC-SHA256(timestamp + body). Retorna True em 2xx."""
    body_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    signature = hmac.new(
        config.secret.encode(),
        f"{timestamp}.".encode() + body_bytes,
        "sha256",
    ).hexdigest()
    response = requests.post(
        config.url,
        data=body_bytes,
        headers={
            "Content-Type": "application/json",
            SIGNATURE_HEADER: f"t={timestamp},v1={signature}",
            TIMESTAMP_HEADER: timestamp,
            EVENT_HEADER: event,
            DELIVERY_HEADER: _delivery_id(config),
        },
        timeout=WEBHOOK_TIMEOUT_SECONDS,
    )
    if not 200 <= response.status_code < 300:
        raise WebhookDeliveryError(f"HTTP {response.status_code}")
    return True


def _register_failure(config: WebhookConfig, detail: str) -> None:
    """Registra a última falha sem derrubar a task nem travar outros webhooks."""
    WebhookConfig.objects.filter(pk=config.pk).update(
        last_failure_at=timezone.now(),
        last_failure_detail=detail[:500],
    )


@shared_task(bind=True, max_retries=3, autoretry_for=(Exception,), retry_backoff=True)
def dispatch_webhook_event(self, event, organization_id, appointment_id, occurred_at=None):
    """Dispara o evento para cada config ativa subscrita; idempotente por retry."""
    from scheduling.models import Appointment

    now = timezone.now()
    occurred = now if occurred_at is None else occurred_at
    occurred_iso = occurred if isinstance(occurred, str) else occurred.isoformat()
    appointment = (
        Appointment.objects.filter(pk=appointment_id, organization_id=organization_id)
        .select_related("organization")
        .first()
    )
    if appointment is None:
        return 0

    configs = list(
        WebhookConfig.objects.filter(
            organization_id=organization_id,
            is_active=True,
            events__contains=[event],
        ).order_by("pk")
    )
    delivered = 0
    for config in configs:
        payload = _appointment_webhook_payload(event, appointment, occurred)
        # Chave de idempotência = evento + webhook_config_id + agendamento:
        # um retry (Celery ou manual) da MESMA entrega nunca duplica o envio,
        # enquanto novos agendamentos continuam disparando normalmente.
        claim_id = claim_side_effect(
            organization=appointment.organization,
            context=f"webhook_{event}",
            key=f"{config.pk}:{appointment.pk}",
            data={
                "appointment_id": appointment.pk,
                "occurred_at": occurred_iso,
                "url": config.url,
            },
        )
        if claim_id is None:
            continue  # já entregue nesta config (retry/rejeito de duplicata)
        try:
            _deliver(config, event, payload)
        except (requests.RequestException, WebhookDeliveryError) as error:
            detail = (
                f"WebhookDeliveryError: {error}"
                if isinstance(error, WebhookDeliveryError)
                else f"{type(error).__name__}: {error}"
            )
            _register_failure(config, detail)
            # Libera a claim: sem retry automático nesta fase, uma nova
            # tentativa (evento posterior/reexecução) pode reenviar.
            release_side_effects([claim_id])
            logger.warning("Webhook %s falhou para config %s: %s", event, config.pk, detail)
            continue
        WebhookConfig.objects.filter(pk=config.pk).update(
            last_failure_at=None, last_failure_detail=""
        )
        complete_side_effect(claim_id)
        delivered += 1
    return delivered
