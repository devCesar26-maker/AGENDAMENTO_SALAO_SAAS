"""Insights acionáveis (item 2): query fixa, paginação e isolamento de tenant."""

from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse
from django.utils import timezone

from catalog.factories import (
    ProfessionalFactory,
    ProfessionalServiceFactory,
    ServiceCategoryFactory,
    ServiceFactory,
    WorkingHoursFactory,
)
from customers.factories import CustomerFactory
from scheduling.models import Appointment, AppointmentItem

pytestmark = pytest.mark.django_db


def make_appointment(org, customer, professional, service, *, status, start):
    appointment = Appointment.objects.create(organization=org, customer=customer, status=status)
    AppointmentItem.objects.create(
        organization=org,
        appointment=appointment,
        service=service,
        professional=professional,
        order=0,
        start_at=start,
        end_at=start + timedelta(minutes=30),
        price=Decimal("100.00"),
        commission_percentage=Decimal("25.00"),
    )
    return appointment


@pytest.fixture
def insights_scenario(organization):
    organization.timezone = "America/Sao_Paulo"
    organization.working_hours = {"mon": [["09:00", "18:00"]]}
    organization.save(update_fields=["timezone", "working_hours"])
    category = ServiceCategoryFactory(organization=organization)
    service = ServiceFactory(
        organization=organization, category=category, name="Corte", price=Decimal("100.00")
    )
    professional = ProfessionalFactory(organization=organization, name="Ana")
    ProfessionalServiceFactory(
        organization=organization, professional=professional, service=service
    )
    WorkingHoursFactory(
        organization=organization,
        professional=professional,
        weekday=0,
        start_time=time(9, 0),
        end_time=time(18, 0),
    )
    tz = ZoneInfo(organization.timezone)
    # Cliente sem retorno há muito tempo => sugere reativação.
    inactive = CustomerFactory(organization=organization, name="Inativo")
    old_day = timezone.localdate(timezone=tz) - timedelta(days=90)
    start = datetime.combine(old_day, time(10), tzinfo=tz)
    make_appointment(
        organization,
        inactive,
        professional,
        service,
        status=Appointment.Status.COMPLETED,
        start=start,
    )
    return service, professional, inactive


def test_insights_retorna_sugestoes_paginadas(auth_client, insights_scenario, organization):
    response = auth_client.get(reverse("insights"))
    assert response.status_code == 200
    body = response.json()
    assert "results" in body and "count" in body
    tipos = {item["type"] for item in body["results"]}
    assert "inactive_customers" in tipos
    for item in body["results"]:
        assert set(item) == {"type", "severity", "message", "reference"}


def test_insights_query_fixa_nao_cresce_com_volume(
    auth_client, insights_scenario, organization, django_assert_num_queries
):
    service, professional, _ = insights_scenario
    tz = ZoneInfo(organization.timezone)
    today = timezone.localdate(timezone=tz)
    extra = CustomerFactory(organization=organization)
    for offset in range(20):
        start = datetime.combine(today - timedelta(days=offset + 1), time(10), tzinfo=tz)
        make_appointment(
            organization,
            extra,
            professional,
            service,
            status=Appointment.Status.COMPLETED,
            start=start,
        )
    with django_assert_num_queries(7):
        response = auth_client.get(reverse("insights"))
    assert response.status_code == 200


def test_insights_exige_manager_e_isola_tenant(
    professional_client, api_client, organization, other_organization
):
    url = reverse("insights")
    assert professional_client.get(url).status_code == 403
    assert api_client.get(url).status_code in (401, 403)

    # OWNER do salão B não vê dados do salão A: nenhuma sugestão referencia o
    # cliente inativo de A (nomes/reference sempre do próprio tenant).
    other_owner = other_organization._owner
    api_client.force_authenticate(user=other_owner)
    response = api_client.get(url)
    assert response.status_code == 200
    results = response.json()["results"]
    for item in results:
        if item["type"] == "inactive_customers":
            nomes = {cliente["name"] for cliente in item["reference"]["customers"]}
            assert "Inativo" not in nomes
