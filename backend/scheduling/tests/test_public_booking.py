"""Cobertura da API pública de reserva e do isolamento por tenant."""

from datetime import date, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from catalog.factories import (
    ProfessionalFactory,
    ProfessionalServiceFactory,
    ServiceCategoryFactory,
    ServiceFactory,
    WorkingHoursFactory,
)
from customers.models import Customer
from organizations.factories import OrganizationFactory
from scheduling.models import Appointment, AppointmentItem
from scheduling.services import create_appointment

BOOKING_DAY = date(2026, 10, 19)


def make_public_schedule(organization):
    organization.timezone = "America/Sao_Paulo"
    organization.working_hours = {"mon": [["09:00", "18:00"]]}
    organization.save(update_fields=["timezone", "working_hours"])
    professional = ProfessionalFactory(
        organization=organization, name="Profissional público"
    )
    category = ServiceCategoryFactory(organization=organization)
    service = ServiceFactory(
        organization=organization,
        category=category,
        name="Corte público",
        duration_minutes=30,
        price="75.00",
    )
    ProfessionalServiceFactory(
        organization=organization, professional=professional, service=service
    )
    WorkingHoursFactory(
        organization=organization,
        professional=professional,
        weekday=BOOKING_DAY.weekday(),
        start_time=time(9, 0),
        end_time=time(18, 0),
    )
    return category, service, professional


def public_headers(organization):
    return {"HTTP_X_TENANT_SLUG": organization.slug}


@pytest.mark.django_db
def test_reserva_publica_grava_consentimento_e_forca_origem(api_client, organization):
    _, service, professional = make_public_schedule(organization)
    response = api_client.get(
        reverse("public-availability"),
        {"services": service.pk, "professional": professional.pk, "date": BOOKING_DAY},
        **public_headers(organization),
    )
    assert response.status_code == 200
    start_at = response.json()["slots"][0]["start_at"]

    response = api_client.post(
        reverse("public-appointment-create"),
        {
            "name": "  Cliente Público  ",
            "phone": "+55 (11) 99999-1111",
            "email": "CLIENTE@example.com",
            "consent": True,
            "start_at": start_at,
            "items": [
                {"service": service.pk, "professional": professional.pk, "order": 0}
            ],
            "origin": Appointment.Origin.DASHBOARD,
        },
        format="json",
        **public_headers(organization),
    )
    assert response.status_code == 201, response.json()
    appointment = Appointment.objects.get(pk=response.json()["id"])
    customer = Customer.objects.get(organization=organization, phone="+5511999991111")
    assert appointment.origin == Appointment.Origin.PUBLIC_PAGE
    assert appointment.created_by is None
    assert appointment.customer_id == customer.pk
    assert customer.name == "Cliente Público"
    assert customer.email == "cliente@example.com"
    assert customer.lgpd_consent is True
    assert customer.lgpd_consent_at is not None
    assert abs((customer.lgpd_consent_at - appointment.created_at).total_seconds()) < 5


@pytest.mark.django_db
def test_chave_idempotente_retorna_a_mesma_reserva_sem_duplicar(
    api_client, organization
):
    _, service, professional = make_public_schedule(organization)
    start_at = api_client.get(
        reverse("public-availability"),
        {"services": service.pk, "professional": professional.pk, "date": BOOKING_DAY},
        **public_headers(organization),
    ).json()["slots"][0]["start_at"]
    payload = {
        "name": "Cliente idempotente",
        "phone": "11955554444",
        "email": "idempotente@example.com",
        "consent": True,
        "start_at": start_at,
        "items": [{"service": service.pk, "professional": professional.pk, "order": 0}],
    }
    headers = {
        **public_headers(organization),
        "HTTP_IDEMPOTENCY_KEY": "booking-retry-123",
    }

    first = api_client.post(
        reverse("public-appointment-create"), payload, format="json", **headers
    )
    second = api_client.post(
        reverse("public-appointment-create"), payload, format="json", **headers
    )

    assert first.status_code == second.status_code == 201
    assert second.json() == first.json()
    assert Appointment.objects.filter(organization=organization).count() == 1


@pytest.mark.django_db
def test_mesma_chave_com_payload_diferente_retorna_conflito(api_client, organization):
    _, service, professional = make_public_schedule(organization)
    slots = api_client.get(
        reverse("public-availability"),
        {"services": service.pk, "professional": professional.pk, "date": BOOKING_DAY},
        **public_headers(organization),
    ).json()["slots"]
    headers = {**public_headers(organization), "HTTP_IDEMPOTENCY_KEY": "reused-key"}
    base = {
        "name": "Cliente",
        "phone": "11955554445",
        "consent": True,
        "items": [{"service": service.pk, "professional": professional.pk, "order": 0}],
    }
    first = api_client.post(
        reverse("public-appointment-create"),
        {**base, "start_at": slots[0]["start_at"]},
        format="json",
        **headers,
    )
    second = api_client.post(
        reverse("public-appointment-create"),
        {**base, "start_at": slots[2]["start_at"]},
        format="json",
        **headers,
    )
    assert first.status_code == 201
    assert second.status_code == 409
    assert Appointment.objects.filter(organization=organization).count() == 1


@pytest.mark.django_db
def test_reserva_publica_nao_altera_identidade_de_cliente_existente(
    api_client, organization
):
    _, service, professional = make_public_schedule(organization)
    customer = Customer.objects.create(
        organization=organization,
        name="Cliente conhecido",
        phone="11988880000",
        email="cliente-conhecido@example.com",
    )
    start_at = api_client.get(
        reverse("public-availability"),
        {"services": service.pk, "professional": professional.pk, "date": BOOKING_DAY},
        **public_headers(organization),
    ).json()["slots"][0]["start_at"]
    response = api_client.post(
        reverse("public-appointment-create"),
        {
            "name": "Pessoa tentando se passar pelo cliente",
            "phone": customer.phone,
            "email": "atacante@example.com",
            "consent": True,
            "start_at": start_at,
            "items": [
                {"service": service.pk, "professional": professional.pk, "order": 0}
            ],
        },
        format="json",
        **public_headers(organization),
    )
    customer.refresh_from_db()
    assert response.status_code == 400
    assert customer.name == "Cliente conhecido"
    assert customer.phone == "11988880000"
    assert customer.email == "cliente-conhecido@example.com"


@pytest.mark.django_db
def test_availability_rejeita_lista_de_servicos_excessiva(api_client, organization):
    _, _, professional = make_public_schedule(organization)
    response = api_client.get(
        reverse("public-availability"),
        {
            "services": ",".join(str(index) for index in range(1, 7)),
            "professional": professional.pk,
            "date": BOOKING_DAY,
        },
        **public_headers(organization),
    )
    assert response.status_code == 400
    assert "no máximo 5" in response.json()["error"]["fields"]["services"][0]


@pytest.mark.django_db
@override_settings(
    PUBLIC_BASE_DOMAIN="salons.example.test", ALLOWED_HOSTS=[".example.test"]
)
def test_host_de_tenant_a_nao_lista_ou_reserva_dados_de_b(api_client, organization):
    category_a, _, professional_a = make_public_schedule(organization)
    organization_b = OrganizationFactory(name="Salão B")
    _, service_b, professional_b = make_public_schedule(organization_b)
    service_b.name = "Serviço exclusivo B"
    service_b.save(update_fields=["name"])
    host_header = {"HTTP_HOST": f"{organization.slug}.salons.example.test"}

    catalog = api_client.get(reverse("public-catalog"), **host_header)
    assert catalog.status_code == 200
    assert "Corte público" in [item["name"] for item in catalog.json()["services"]]
    assert service_b.name not in [item["name"] for item in catalog.json()["services"]]
    assert category_a.name in [item["name"] for item in catalog.json()["categories"]]

    forged_availability = api_client.get(
        reverse("public-availability"),
        {
            "services": service_b.pk,
            "professional": professional_b.pk,
            "date": BOOKING_DAY,
        },
        **host_header,
        HTTP_X_TENANT_SLUG=organization_b.slug,
    )
    assert forged_availability.status_code == 404

    response = api_client.get(
        reverse("public-professionals"),
        **host_header,
    )
    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == [professional_a.name]


@pytest.mark.django_db
def test_rotas_publicas_nao_exigem_autenticacao_e_limitam_por_ip(
    api_client, organization
):
    make_public_schedule(organization)
    cache.clear()
    statuses = [
        api_client.get(
            reverse("public-catalog"), **public_headers(organization)
        ).status_code
        for _ in range(11)
    ]
    assert statuses[:10] == [200] * 10
    assert statuses[10] == 429


@pytest.mark.django_db
def test_cliente_publico_tem_limite_de_tres_reservas_em_24_horas(
    api_client, organization
):
    _, service, professional = make_public_schedule(organization)
    slots = api_client.get(
        reverse("public-availability"),
        {"services": service.pk, "professional": professional.pk, "date": BOOKING_DAY},
        **public_headers(organization),
    ).json()["slots"]
    base_payload = {
        "name": "Cliente limite",
        "phone": "11988887777",
        "email": "limite@example.com",
        "consent": True,
        "items": [{"service": service.pk, "professional": professional.pk, "order": 0}],
    }
    for index, slot in enumerate(slots[::2][:4]):
        response = api_client.post(
            reverse("public-appointment-create"),
            {**base_payload, "start_at": slot["start_at"]},
            format="json",
            **public_headers(organization),
        )
        expected = 429 if index == 3 else 201
        assert response.status_code == expected, response.json()
        if expected == 429:
            assert "Limite de reservas" in response.json()["error"]["detail"]
    assert Appointment.objects.filter(organization=organization).count() == 3


@pytest.mark.django_db
def test_cliente_com_historico_concluido_pode_agendar_ate_quatro_vezes_em_24_horas(
    api_client, organization
):
    _, service, professional = make_public_schedule(organization)
    slots = api_client.get(
        reverse("public-availability"),
        {"services": service.pk, "professional": professional.pk, "date": BOOKING_DAY},
        **public_headers(organization),
    ).json()["slots"]
    customer = Customer.objects.create(
        organization=organization,
        name="Cliente recorrente",
        phone="11966665555",
        email="recorrente@example.com",
    )
    completed = Appointment.objects.create(
        organization=organization,
        customer=customer,
        status=Appointment.Status.COMPLETED,
    )
    Appointment.objects.filter(pk=completed.pk).update(
        created_at=timezone.now() - timedelta(days=2)
    )
    payload = {
        "name": customer.name,
        "phone": customer.phone,
        "email": customer.email,
        "consent": True,
        "items": [{"service": service.pk, "professional": professional.pk, "order": 0}],
    }

    for index, slot in enumerate(slots[::2][:5]):
        response = api_client.post(
            reverse("public-appointment-create"),
            {**payload, "start_at": slot["start_at"]},
            format="json",
            **public_headers(organization),
        )
        expected = 429 if index == 4 else 201
        assert response.status_code == expected, response.json()
        if expected == 429:
            assert "Limite de reservas" in response.json()["error"]["detail"]

    assert (
        Appointment.objects.filter(organization=organization, customer=customer).count()
        == 5
    )


@pytest.mark.django_db
def test_remarcar_conflito_retorna_409_e_slot_livre_atualiza(auth_client, organization):
    professional = ProfessionalFactory(
        organization=organization, user=organization._owner
    )
    category = ServiceCategoryFactory(organization=organization)
    service = ServiceFactory(
        organization=organization, category=category, duration_minutes=30, price="50.00"
    )
    ProfessionalServiceFactory(
        organization=organization, professional=professional, service=service
    )
    WorkingHoursFactory(
        organization=organization,
        professional=professional,
        weekday=BOOKING_DAY.weekday(),
        start_time=time(9, 0),
        end_time=time(18, 0),
    )
    organization.working_hours = {"mon": [["09:00", "18:00"]]}
    organization.save(update_fields=["working_hours"])
    customer = Customer.objects.create(
        organization=organization, name="Cliente", phone="11977776666"
    )
    tz = ZoneInfo(organization.timezone)

    def book(hour):
        from datetime import datetime

        return create_appointment(
            organization=organization,
            customer=customer,
            items=[{"service": service, "professional": professional, "order": 0}],
            desired_start=datetime(2026, 10, 19, hour, 0, tzinfo=tz),
            membership=organization.memberships.get(user=organization._owner),
        )

    moving = book(9)
    book(11)
    conflict = auth_client.patch(
        reverse("appointment-reschedule", kwargs={"pk": moving.pk}),
        {"start_at": "2026-10-19T11:00:00-03:00"},
        format="json",
    )
    assert conflict.status_code == 409
    assert "horário" in conflict.json()["error"]["detail"].lower()

    moved = auth_client.patch(
        reverse("appointment-reschedule", kwargs={"pk": moving.pk}),
        {"start_at": "2026-10-19T10:00:00-03:00"},
        format="json",
    )
    assert moved.status_code == 200, moved.json()
    item = AppointmentItem.objects.get(appointment=moving)
    assert item.start_at.astimezone(tz).hour == 10
