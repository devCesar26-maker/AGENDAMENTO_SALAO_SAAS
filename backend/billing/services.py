"""Regras de negócio de billing, limites e integração Mercado Pago."""

import hashlib
import hmac
import json
from datetime import datetime, timedelta

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from billing import selectors
from billing.models import Plan, PlanTier, Subscription, SubscriptionStatus
from core.idempotency import IdempotencyConflict, execute_idempotently
from organizations.models import Organization


class PaymentProviderError(APIException):
    status_code = 502
    default_detail = "Não foi possível iniciar o checkout no Mercado Pago."
    default_code = "payment_provider_error"


class PlanLimitExceeded(APIException):
    status_code = 402
    default_code = "plan_limit_exceeded"

    def __init__(self, resource, limit, usage):
        super().__init__(
            {
                "detail": f"Limite do plano atingido para {resource}.",
                "limit": limit,
                "usage": usage,
            }
        )


def get_subscription(organization):
    subscription = selectors.get_subscription(organization)
    if subscription:
        return subscription
    subscription, _ = Subscription.objects.get_or_create(
        organization=organization,
        defaults={"plan": Plan.objects.get(tier=PlanTier.FREE)},
    )
    return Subscription.objects.select_related("plan").get(pk=subscription.pk)


def monthly_usage(organization):
    return selectors.get_monthly_usage(organization)


def _enforce_limit(*, resource, used, limit):
    if limit is not None and used >= limit:
        raise PlanLimitExceeded(resource, limit, used)


@transaction.atomic
def check_professional_limit(organization):
    Organization.objects.select_for_update().only("pk").get(pk=organization.pk)
    subscription = get_subscription(organization)
    used = monthly_usage(organization)["professionals"]
    _enforce_limit(
        resource="profissionais",
        used=used,
        limit=subscription.plan.max_professionals,
    )


@transaction.atomic
def check_appointment_limit(organization):
    Organization.objects.select_for_update().only("pk").get(pk=organization.pk)
    subscription = get_subscription(organization)
    usage = monthly_usage(organization)
    _enforce_limit(
        resource="agendamentos neste mês",
        used=usage["appointments"],
        limit=subscription.plan.max_appointments_per_month,
    )


def _mp_request(url, *, method="GET", payload=None):
    token = getattr(settings, "MP_ACCESS_TOKEN", "")
    if not token:
        raise PaymentProviderError("Mercado Pago não configurado (MP_ACCESS_TOKEN).")
    headers = {"Authorization": f"Bearer {token}"}
    try:
        if method == "POST":
            response = requests.post(url, json=payload, headers=headers, timeout=10, verify=True)
        else:
            response = requests.get(url, headers=headers, timeout=10, verify=True)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as error:
        raise PaymentProviderError() from error


def create_checkout(*, organization, tier):
    if tier not in (PlanTier.PLUS, PlanTier.PREMIUM):
        raise ValidationError({"tier": "Escolha PLUS ou PREMIUM."})
    plan = Plan.objects.get(tier=tier)
    payload = {
        "reason": f"Plano {plan.nome_para(organization)}",
        "external_reference": f"{organization.pk}:{tier}",
        "back_url": f"{settings.FRONTEND_URL.rstrip('/')}/billing/retorno",
        "auto_recurring": {
            "frequency": 1,
            "frequency_type": "months",
            "transaction_amount": plan.monthly_price_cents / 100,
            "currency_id": "BRL",
        },
        "payer_email": organization.memberships.filter(role="OWNER", is_active=True)
        .select_related("user")
        .values_list("user__email", flat=True)
        .first(),
        "status": "pending",
    }
    result = _mp_request("https://api.mercadopago.com/preapproval", method="POST", payload=payload)
    checkout_url = result.get("sandbox_init_point") or result.get("init_point")
    if not result.get("id") or not checkout_url:
        raise PaymentProviderError()
    return {"checkout_url": checkout_url}


def verify_webhook_signature(*, body, event_id, signature, request_id, secret):
    if not signature or not request_id or not secret:
        return False
    try:
        body_id = str(json.loads(body).get("data", {}).get("id", "")).lower()
        event_id = str(event_id or body_id).lower()
        if body_id and body_id != event_id:
            return False
        pieces = dict(part.strip().split("=", 1) for part in signature.split(","))
        timestamp, received = pieces["ts"], pieces["v1"]
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return False
    manifest = f"id:{event_id};request-id:{request_id};ts:{timestamp};"
    expected = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return bool(event_id and hmac.compare_digest(expected, received))


@transaction.atomic
def _apply_notification(payload):
    event_id = str(payload.get("data", {}).get("id", ""))
    if not event_id:
        raise ValidationError("Notificação sem ID de evento.")
    preapproval = _mp_request(f"https://api.mercadopago.com/preapproval/{event_id}")
    try:
        organization_id, tier = preapproval["external_reference"].split(":", 1)
        organization = Organization.objects.select_for_update().get(pk=organization_id)
        plan = Plan.objects.get(tier=tier)
    except (
        KeyError,
        ValueError,
        Organization.DoesNotExist,
        Plan.DoesNotExist,
    ) as error:
        raise ValidationError("Referência de assinatura inválida.") from error
    status_value = preapproval.get("status")
    subscription, _ = Subscription.objects.select_for_update().get_or_create(
        organization=organization,
        defaults={"plan": Plan.objects.get(tier=PlanTier.FREE)},
    )
    if status_value == "authorized":
        subscription.plan = plan
        subscription.status = SubscriptionStatus.ACTIVE
    elif status_value in {"cancelled", "canceled"}:
        subscription.plan = Plan.objects.get(tier=PlanTier.FREE)
        subscription.status = SubscriptionStatus.CANCELED
    elif status_value in {"paused", "pending"}:
        subscription.plan = Plan.objects.get(tier=PlanTier.FREE)
        subscription.status = SubscriptionStatus.PAST_DUE
    else:
        return {"received": True, "ignored": True}
    subscription.mercadopago_subscription_id = event_id
    start = preapproval.get("date_created")
    end = preapproval.get("next_payment_date")
    subscription.current_period_start = (
        datetime.fromisoformat(start.replace("Z", "+00:00")) if start else timezone.now()
    )
    subscription.current_period_end = (
        datetime.fromisoformat(end.replace("Z", "+00:00")) if end else None
    )
    subscription.save()
    return {"received": True}


def process_webhook(payload):
    """Deduplica notificações por ID do evento, distinto do ID do recurso."""
    event_id = str(payload.get("id") or payload.get("data", {}).get("id", ""))
    if not event_id or not payload.get("data", {}).get("id"):
        raise ValidationError("Notificação sem ID de evento.")
    try:
        result, _ = execute_idempotently(
            organization=None,
            context="mercadopago_webhook",
            key=event_id,
            data=payload,
            operation=lambda: _apply_notification(payload),
            ttl=timedelta(days=3650),
        )
    except IdempotencyConflict as error:
        raise ValidationError("ID de notificação reutilizado com conteúdo diferente.") from error
    return result
