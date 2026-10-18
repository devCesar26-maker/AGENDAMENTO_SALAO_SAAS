import hashlib
import hmac
import json
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from billing.models import Plan, PlanTier, Subscription, SubscriptionStatus
from billing.services import (
    PlanLimitExceeded,
    check_appointment_limit,
    check_professional_limit,
    process_webhook,
)
from catalog.factories import (
    ProfessionalFactory,
    ProfessionalServiceFactory,
    ServiceCategoryFactory,
    ServiceFactory,
    WorkingHoursFactory,
)
from customers.factories import CustomerFactory
from organizations.factories import MembershipFactory, OrganizationFactory
from scheduling.models import Appointment
from scheduling.services import create_appointment

pytestmark = pytest.mark.django_db


def set_tier(organization, tier):
    subscription, _ = Subscription.objects.get_or_create(
        organization=organization,
        defaults={"plan": Plan.objects.get(tier=PlanTier.FREE)},
    )
    subscription.plan = Plan.objects.get(tier=tier)
    subscription.save()
    return subscription


def test_free_professional_limit_blocks_creation_without_deleting_existing(
    auth_client, organization
):
    set_tier(organization, PlanTier.FREE)
    response = auth_client.post(
        reverse("professional-list"), {"name": "Primeira"}, format="json"
    )
    assert response.status_code == status.HTTP_201_CREATED
    blocked = auth_client.post(
        reverse("professional-list"), {"name": "Segunda"}, format="json"
    )
    assert blocked.status_code == 402
    assert int(blocked.json()["error"]["limit"]) == 1
    assert int(blocked.json()["error"]["usage"]) == 1


def test_downgrade_preserves_professionals_and_blocks_new_ones(
    auth_client, organization
):
    set_tier(organization, PlanTier.PLUS)
    first = ProfessionalFactory(organization=organization)
    ProfessionalFactory(organization=organization)
    set_tier(organization, PlanTier.FREE)
    response = auth_client.post(
        reverse("professional-list"), {"name": "Outra"}, format="json"
    )
    assert response.status_code == 402
    assert first.__class__.objects.filter(organization=organization).count() == 2


def test_plans_use_vertical_display_names(auth_client, organization, api_client):
    salon = auth_client.get(reverse("billing-plans"))
    assert {item["tier"]: item["name"] for item in salon.json()}["PLUS"] == "Allure"
    barber_org = OrganizationFactory(vertical="BARBEARIA")
    owner = MembershipFactory(organization=barber_org, role="OWNER").user
    api_client.force_authenticate(user=owner)
    barber = api_client.get(reverse("billing-plans"))
    names = {item["tier"]: item["name"] for item in barber.json()}
    assert names == {"FREE": "Free", "PLUS": "Artisan", "PREMIUM": "Confrérie"}


def test_usage_endpoint_reports_tenant_scoped_counts(auth_client, organization):
    set_tier(organization, PlanTier.FREE)
    ProfessionalFactory(organization=organization)
    other = OrganizationFactory()
    other_customer = CustomerFactory(organization=other)
    ProfessionalFactory(organization=other)
    Appointment.objects.create(organization=other, customer=other_customer)
    response = auth_client.get(reverse("billing-usage"))
    assert response.status_code == 200
    assert response.json()["professionals"] == {"used": 1, "limit": 1}
    assert response.json()["appointments"]["used"] == 0


def test_canceled_appointments_restore_monthly_quota(organization, auth_client):
    set_tier(organization, PlanTier.FREE)
    tomorrow = timezone.localdate() + timedelta(days=1)
    weekday = tomorrow.weekday()
    day_keys = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    organization.working_hours = {day_keys[weekday]: [["09:00", "18:00"]]}
    organization.save(update_fields=["working_hours", "updated_at"])
    membership = MembershipFactory(organization=organization, role="OWNER")
    professional = ProfessionalFactory(organization=organization)
    category = ServiceCategoryFactory(organization=organization)
    service = ServiceFactory(
        organization=organization, category=category, duration_minutes=30
    )
    ProfessionalServiceFactory(
        organization=organization, professional=professional, service=service
    )
    WorkingHoursFactory(
        organization=organization,
        professional=professional,
        weekday=weekday,
        start_time=time(9),
        end_time=time(18),
    )
    customer = CustomerFactory(organization=organization)
    desired_start = datetime.combine(
        tomorrow, time(10), tzinfo=ZoneInfo(organization.timezone)
    )
    created = create_appointment(
        organization=organization,
        customer=customer,
        items=[{"service": service, "professional": professional, "order": 0}],
        desired_start=desired_start,
        membership=membership,
    )
    assert created.pk
    Appointment.objects.bulk_create(
        [Appointment(organization=organization, customer=customer) for _ in range(49)]
    )
    with pytest.raises(PlanLimitExceeded):
        create_appointment(
            organization=organization,
            customer=customer,
            items=[{"service": service, "professional": professional, "order": 0}],
            desired_start=desired_start + timedelta(hours=1),
            membership=membership,
        )
    assert Appointment.objects.filter(organization=organization).count() == 50

    canceled_ids = list(
        Appointment.objects.filter(organization=organization)
        .exclude(status=Appointment.Status.CANCELED)
        .order_by("pk")
        .values_list("pk", flat=True)[:10]
    )
    Appointment.objects.filter(pk__in=canceled_ids).update(
        status=Appointment.Status.CANCELED
    )
    usage = auth_client.get(reverse("billing-usage"))
    assert usage.status_code == status.HTTP_200_OK
    assert usage.json()["appointments"]["used"] == 40

    next_appointment = create_appointment(
        organization=organization,
        customer=customer,
        items=[{"service": service, "professional": professional, "order": 0}],
        desired_start=desired_start + timedelta(hours=1),
        membership=membership,
    )
    assert next_appointment.pk
    assert (
        auth_client.get(reverse("billing-usage")).json()["appointments"]["used"] == 41
    )


def test_appointment_monthly_limit_rejects_at_limit(organization):
    set_tier(organization, PlanTier.FREE)
    customer = CustomerFactory(organization=organization)
    Appointment.objects.bulk_create(
        [Appointment(organization=organization, customer=customer) for _ in range(50)]
    )
    with pytest.raises(PlanLimitExceeded):
        check_appointment_limit(organization)


def test_professional_limit_allows_creation_inside_limit(organization):
    set_tier(organization, PlanTier.FREE)
    check_professional_limit(organization)
    ProfessionalFactory(organization=organization)
    with pytest.raises(PlanLimitExceeded):
        check_professional_limit(organization)


def _signed_headers(body, request_id, secret):
    event_id = str(json.loads(body)["data"]["id"]).lower()
    timestamp = "1704908010"
    manifest = f"id:{event_id};request-id:{request_id};ts:{timestamp};"
    digest = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return {
        "HTTP_X_SIGNATURE": f"ts={timestamp},v1={digest}",
        "HTTP_X_REQUEST_ID": request_id,
    }


@override_settings(MP_WEBHOOK_SECRET="hook-secret")
def test_webhook_rejects_invalid_signature(api_client):
    response = api_client.post(
        reverse("billing-mercadopago-webhook"),
        data=json.dumps({"data": {"id": "event-123"}}),
        content_type="application/json",
        HTTP_X_SIGNATURE="ts=1,v1=bad",
        HTTP_X_REQUEST_ID="request-1",
    )
    assert response.status_code == 401


def test_webhook_idempotent_and_downgrade_keeps_data(organization, monkeypatch):
    subscription = set_tier(organization, PlanTier.PLUS)
    professional = ProfessionalFactory(organization=organization)
    payload = {
        "id": "notification-44-authorized",
        "type": "subscription_preapproval",
        "data": {"id": "subscription-44"},
    }
    calls = []
    statuses = iter(("authorized", "cancelled"))

    def mp_get(url, **kwargs):
        calls.append(url)
        return {
            "external_reference": f"{organization.pk}:PLUS",
            "status": next(statuses),
            "date_created": "2026-10-01T12:00:00Z",
        }

    monkeypatch.setattr("billing.services._mp_request", mp_get)
    assert process_webhook(payload) == {"received": True}
    assert process_webhook(payload) == {"received": True}
    cancellation = {**payload, "id": "notification-44-cancelled"}
    assert process_webhook(cancellation) == {"received": True}
    subscription.refresh_from_db()
    assert subscription.plan.tier == PlanTier.FREE
    assert subscription.status == SubscriptionStatus.CANCELED
    assert ProfessionalFactory._meta.model.objects.filter(pk=professional.pk).exists()
    assert calls == [
        "https://api.mercadopago.com/preapproval/subscription-44",
        "https://api.mercadopago.com/preapproval/subscription-44",
    ]


def test_webhook_signature_accepts_official_manifest():
    from billing.services import verify_webhook_signature

    body = b'{"data":{"id":"abc-123"}}'
    headers = _signed_headers(body, "request-abc", "secret")
    assert verify_webhook_signature(
        body=body,
        event_id="abc-123",
        signature=headers["HTTP_X_SIGNATURE"],
        request_id="request-abc",
        secret="secret",
    )
