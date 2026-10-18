import csv
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.factories import UserFactory
from analytics.models import AuditLog
from catalog.factories import (
    ProfessionalFactory,
    ProfessionalServiceFactory,
    ServiceCategoryFactory,
    ServiceFactory,
)
from catalog.models import ProfessionalService
from customers.factories import CustomerFactory
from organizations.factories import MembershipFactory, OrganizationFactory
from scheduling.models import Appointment, AppointmentItem

pytestmark = pytest.mark.django_db


def make_appointment(org, customer, professional, service, *, status, start, price="100.00"):
    appointment = Appointment.objects.create(organization=org, customer=customer, status=status)
    AppointmentItem.objects.create(
        organization=org,
        appointment=appointment,
        service=service,
        professional=professional,
        order=0,
        start_at=start,
        end_at=start + timedelta(minutes=30),
        price=Decimal(price),
        commission_percentage=Decimal("25.00"),
    )
    return appointment


@pytest.fixture
def scenario(organization):
    professional_user = UserFactory()
    MembershipFactory(organization=organization, user=professional_user, role="PROFESSIONAL")
    professional = ProfessionalFactory(
        organization=organization, user=professional_user, name="Ana"
    )
    category = ServiceCategoryFactory(organization=organization)
    service = ServiceFactory(
        organization=organization, category=category, name="Corte", price=Decimal("100.00")
    )
    link = ProfessionalServiceFactory(
        organization=organization,
        professional=professional,
        service=service,
        commission_percentage=Decimal("25.00"),
    )
    customer = CustomerFactory(organization=organization, name="Cliente A")
    start = timezone.localtime(timezone.now(), timezone=ZoneInfo(organization.timezone)).replace(
        hour=12, minute=0, second=0, microsecond=0
    )
    weekday = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")[start.weekday()]
    organization.working_hours = {weekday: [["12:00", "13:00"]]}
    organization.save(update_fields=["working_hours", "updated_at"])
    completed = make_appointment(
        organization,
        customer,
        professional,
        service,
        status=Appointment.Status.COMPLETED,
        start=start,
    )
    make_appointment(
        organization,
        customer,
        professional,
        service,
        status=Appointment.Status.NO_SHOW,
        start=start + timedelta(hours=1),
    )
    return organization, professional, service, link, customer, completed, start


def test_metrics_known_values_and_professional_scope(auth_client, scenario, organization):
    org, professional, service, _, _, _, start = scenario
    start_date = start.astimezone(ZoneInfo(org.timezone)).date().isoformat()
    end_date = start_date
    response = auth_client.get(
        reverse("metrics-overview"), {"data_inicio": start_date, "data_fim": end_date}
    )
    assert response.status_code == 200
    assert response.json() == {
        "total_appointments": 2,
        "occupancy_rate": 100.0,
        "no_show_rate": 50.0,
        "estimated_revenue": "100.00",
    }
    ranking = auth_client.get(
        reverse("metrics-services"), {"data_inicio": start_date, "data_fim": end_date}
    )
    assert ranking.json() == [
        {
            "service_id": service.pk,
            "service_name": "Corte",
            "quantity": 1,
            "revenue": "100.00",
        }
    ]
    professionals = auth_client.get(
        reverse("metrics-professionals"), {"data_inicio": start_date, "data_fim": end_date}
    )
    assert professionals.json()[0]["professional_id"] == professional.pk
    professional_client = APIClient()
    professional_client.force_authenticate(user=professional.user)
    professional_response = professional_client.get(
        reverse("metrics-professionals"), {"data_inicio": start_date, "data_fim": end_date}
    )
    assert [row["professional_id"] for row in professional_response.json()] == [professional.pk]

    other = OrganizationFactory()
    other_professional = ProfessionalFactory(organization=other)
    other_customer = CustomerFactory(organization=other)
    other_category = ServiceCategoryFactory(organization=other)
    other_service = ServiceFactory(organization=other, category=other_category)
    make_appointment(
        other,
        other_customer,
        other_professional,
        other_service,
        status=Appointment.Status.COMPLETED,
        start=start,
    )
    assert (
        auth_client.get(
            reverse("metrics-overview"), {"data_inicio": start_date, "data_fim": end_date}
        ).json()["total_appointments"]
        == 2
    )


def test_metrics_query_count_does_not_grow_with_volume(
    auth_client, organization, django_assert_num_queries
):
    professional = ProfessionalFactory(organization=organization)
    category = ServiceCategoryFactory(organization=organization)
    service = ServiceFactory(organization=organization, category=category)
    customer = CustomerFactory(organization=organization)
    start = timezone.now()
    for offset in range(20):
        make_appointment(
            organization,
            customer,
            professional,
            service,
            status=Appointment.Status.COMPLETED,
            start=start + timedelta(minutes=offset * 40),
        )
    params = {"data_inicio": start.date().isoformat(), "data_fim": start.date().isoformat()}
    with django_assert_num_queries(5):
        assert auth_client.get(reverse("metrics-overview"), params).status_code == 200
    with django_assert_num_queries(2):
        assert auth_client.get(reverse("metrics-services"), params).status_code == 200
    with django_assert_num_queries(2):
        assert auth_client.get(reverse("metrics-professionals"), params).status_code == 200


def test_exports_are_csv_and_tenant_scoped(auth_client, organization, scenario):
    _org, professional, service, _, customer, appointment, start = scenario
    other = OrganizationFactory()
    other_customer = CustomerFactory(organization=other, name="SEGREDO OUTRO TENANT")
    other_professional = ProfessionalFactory(organization=other)
    other_category = ServiceCategoryFactory(organization=other)
    other_service = ServiceFactory(organization=other, category=other_category)
    make_appointment(
        other,
        other_customer,
        other_professional,
        other_service,
        status=Appointment.Status.COMPLETED,
        start=start,
    )
    params = {"data_inicio": start.date().isoformat(), "data_fim": start.date().isoformat()}
    appointments = auth_client.get(reverse("export-appointments"), params)
    assert appointments.status_code == 200
    assert appointments.streaming
    rows = list(csv.reader(StringIO(b"".join(appointments.streaming_content).decode("utf-8-sig"))))
    assert len(rows) == 3
    assert {row[0] for row in rows[1:]} == {
        str(appointment.pk),
        str(appointment.pk + 1),
    }
    assert all("Cliente A" in row for row in rows[1:])
    assert "SEGREDO OUTRO TENANT" not in str(rows)

    customers = auth_client.get(reverse("export-customers"))
    customer_rows = list(
        csv.reader(StringIO(b"".join(customers.streaming_content).decode("utf-8-sig")))
    )
    assert any(row[1] == customer.name for row in customer_rows[1:])
    assert all(row[1] != other_customer.name for row in customer_rows[1:])

    commissions = auth_client.get(reverse("export-commissions"), params)
    commission_rows = list(
        csv.reader(StringIO(b"".join(commissions.streaming_content).decode("utf-8-sig")))
    )
    assert len(commission_rows) == 2
    assert commission_rows[1][1:4] == [professional.name, service.name, "100.00"]
    assert commission_rows[1][-1] == "25.00"


def test_professional_cannot_export_or_view_audit(professional_client):
    assert professional_client.get(reverse("export-appointments")).status_code == 403
    assert professional_client.get(reverse("export-customers")).status_code == 403
    assert professional_client.get(reverse("export-commissions")).status_code == 403
    assert professional_client.get(reverse("audit-log-list")).status_code == 403


def test_audit_records_appointment_cancellation_once_with_actor(
    auth_client, organization, scenario
):
    _, _, _, _, _, appointment, _ = scenario
    response = auth_client.post(reverse("appointment-cancel", args=[appointment.pk]))
    assert response.status_code == 200
    auth_client.post(reverse("appointment-cancel", args=[appointment.pk]))
    logs = AuditLog.objects.filter(
        organization=organization, action=AuditLog.Action.APPOINTMENT_CANCELED
    )
    assert logs.count() == 1
    assert logs.get().actor.user == organization._owner


def test_audit_member_removal_and_commission_change(auth_client, organization, scenario):
    _, _, _, link, _, _, _ = scenario
    member = MembershipFactory(organization=organization, role="MANAGER")
    response = auth_client.patch(
        reverse("organization-member-detail", args=[organization.slug, member.pk]),
        {"is_active": False},
        format="json",
    )
    assert response.status_code == 200
    response = auth_client.patch(
        reverse("professional-service-detail", args=[link.pk]),
        {"commission_percentage": "30.00"},
        format="json",
    )
    assert response.status_code == 200
    assert (
        AuditLog.objects.filter(organization=organization, action=AuditLog.Action.MEMBER_REMOVED)
        .get()
        .actor.user
        == organization._owner
    )
    assert (
        AuditLog.objects.filter(
            organization=organization, action=AuditLog.Action.COMMISSION_CHANGED
        )
        .get()
        .actor.user
        == organization._owner
    )
    assert ProfessionalService.objects.get(pk=link.pk).commission_percentage == Decimal("30.00")


def test_audit_plan_change_webhook_has_no_actor_and_tenant_scoping(
    organization, auth_client, other_organization, settings
):
    from billing.models import Plan, PlanTier, Subscription
    from billing.services import process_webhook

    settings.MP_ACCESS_TOKEN = "mock-token"
    subscription = Subscription.objects.get(organization=organization)
    subscription.plan = Plan.objects.get(tier=PlanTier.FREE)
    subscription.save(update_fields=["plan", "updated_at"])
    payload = {"id": "audit-event-1", "data": {"id": "subscription-1"}}
    preapproval = {
        "id": "subscription-1",
        "external_reference": f"{organization.pk}:{PlanTier.PLUS}",
        "status": "authorized",
    }
    from unittest.mock import patch

    with patch("billing.services._mp_request", return_value=preapproval):
        process_webhook(payload)
        process_webhook(payload)
    log = AuditLog.objects.get(organization=organization, action=AuditLog.Action.PLAN_CHANGED)
    assert log.actor is None
    assert log.context == {"from_tier": "FREE", "to_tier": "PLUS"}
    assert not AuditLog.objects.filter(organization=other_organization).exists()
    assert Subscription.objects.get(organization=organization).plan.tier == PlanTier.PLUS

    AuditLog.objects.create(
        organization=other_organization,
        action=AuditLog.Action.PLAN_CHANGED,
        object_type="subscription",
        context={"to_tier": "PREMIUM"},
    )
    response = auth_client.get(reverse("audit-log-list"))
    assert response.status_code == 200
    assert all(row["context"] != {"to_tier": "PREMIUM"} for row in response.json()["results"])


def test_audit_context_drops_sensitive_fields(organization):
    from analytics.services import record_audit

    log = record_audit(
        organization=organization,
        action=AuditLog.Action.PLAN_CHANGED,
        object_type="subscription",
        context={"to_tier": "PLUS", "access_token": "never-save", "password": "secret"},
    )
    assert log.context == {"to_tier": "PLUS"}
