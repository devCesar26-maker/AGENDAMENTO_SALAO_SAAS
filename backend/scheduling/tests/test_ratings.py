"""Avaliações pós-atendimento e ranking por preferência do cliente (itens 3 e 4)."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.core import mail
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
from notifications.models import NotificationEvent
from notifications.tasks import dispatch_notification_outbox
from scheduling import services
from scheduling.models import Appointment, AppointmentToken, Rating

WEEKDAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def make_schedule(organization):
    desired_date = timezone.localdate() + timedelta(days=7)
    organization.timezone = "America/Sao_Paulo"
    organization.working_hours = {WEEKDAY_KEYS[desired_date.weekday()]: [["09:00", "18:00"]]}
    organization.save(update_fields=["timezone", "working_hours"])
    category = ServiceCategoryFactory(organization=organization)
    service = ServiceFactory(
        organization=organization,
        category=category,
        name="Corte",
        duration_minutes=30,
        price="75.00",
    )
    professionals = []
    for name in ("Ana", "Bia"):
        professional = ProfessionalFactory(organization=organization, name=name)
        ProfessionalServiceFactory(
            organization=organization, professional=professional, service=service
        )
        WorkingHoursFactory(
            organization=organization,
            professional=professional,
            weekday=desired_date.weekday(),
            start_time=time(9, 0),
            end_time=time(18, 0),
        )
        professionals.append(professional)
    customer = CustomerFactory(organization=organization, email="cliente@example.com")
    start_at = datetime.combine(desired_date, time(10), tzinfo=ZoneInfo(organization.timezone))
    return desired_date, service, professionals, customer, start_at


def completed_appointment(
    organization,
    service,
    professional,
    customer,
    start_at,
    *,
    score=None,
    status=Appointment.Status.COMPLETED,
):
    appointment = Appointment.objects.create(
        organization=organization, customer=customer, status=Appointment.Status.CONFIRMED
    )
    appointment.items.create(
        organization=organization,
        service=service,
        professional=professional,
        order=0,
        start_at=start_at,
        end_at=start_at + timedelta(minutes=30),
        price=service.price,
    )
    appointment.status = status
    appointment.save(update_fields=["status", "updated_at"])
    if score is not None:
        Rating.objects.create(
            organization=organization, appointment=appointment, score=score, comment=""
        )
    return appointment


@pytest.mark.django_db
def test_completar_agendamento_cria_token_e_envia_pedido_de_avaliacao(organization):
    _, service, professionals, customer, start_at = make_schedule(organization)
    appointment = completed_appointment(
        organization,
        service,
        professionals[0],
        customer,
        start_at,
        status=Appointment.Status.CONFIRMED,
    )
    mail.outbox.clear()

    services.change_appointment_status(appointment, Appointment.Status.COMPLETED)
    assert NotificationEvent.objects.filter(appointment=appointment).count() == 1
    token = AppointmentToken.objects.get(
        appointment=appointment, action=AppointmentToken.Action.RATE
    )
    assert token.expires_at > timezone.now()

    assert dispatch_notification_outbox.run() == 1
    assert mail.outbox[0].to == [customer.email]
    assert f"/avaliar/{token.token}" in mail.outbox[0].body


@pytest.mark.django_db
def test_avaliacao_publica_grava_uma_vez_e_consome_token(api_client, organization):
    _, service, professionals, customer, start_at = make_schedule(organization)
    appointment = completed_appointment(organization, service, professionals[0], customer, start_at)
    token = services.ensure_rating_token(appointment)

    response = api_client.get(reverse("public-rating", args=[token.token]))
    assert response.status_code == 200
    assert response.json()["customer_name"] == customer.name

    response = api_client.post(
        reverse("public-rating", args=[token.token]),
        data={"score": 5, "comment": "Ótimo atendimento"},
        format="json",
    )
    assert response.status_code == 201
    rating = Rating.objects.get(appointment=appointment)
    assert rating.score == 5
    token.refresh_from_db()
    assert token.used_at is not None

    replay = api_client.post(
        reverse("public-rating", args=[token.token]),
        data={"score": 1},
        format="json",
    )
    assert replay.status_code == 410
    assert Rating.objects.filter(appointment=appointment).count() == 1


@pytest.mark.django_db
def test_avaliacao_rejeita_token_de_outro_tipo_e_atendimento_nao_concluido(
    api_client, organization
):
    _, service, professionals, customer, start_at = make_schedule(organization)
    appointment = Appointment.objects.create(
        organization=organization, customer=customer, status=Appointment.Status.SCHEDULED
    )
    appointment.items.create(
        organization=organization,
        service=service,
        professional=professionals[0],
        order=0,
        start_at=start_at,
        end_at=start_at + timedelta(minutes=30),
        price=service.price,
    )
    view_token = services.ensure_magic_link_token(appointment)
    assert api_client.get(reverse("public-rating", args=[view_token.token])).status_code == 404


@pytest.mark.django_db
def test_ranking_usa_historico_do_cliente_e_fallback_geral(organization):
    desired_date, service, professionals, customer, start_at = make_schedule(organization)
    ana, bia = professionals
    other_customer = CustomerFactory(organization=organization)

    # Ana tem nota geral média; Bia tem nota específica alta para este cliente.
    completed_appointment(organization, service, ana, other_customer, start_at, score=2)
    completed_appointment(
        organization, service, ana, other_customer, start_at + timedelta(hours=1), score=2
    )
    completed_appointment(
        organization, service, bia, customer, start_at + timedelta(hours=2), score=5
    )

    # Sem cliente, usa a média geral e Ana cai por ter média menor.
    general = services.calcular_slots_disponiveis(organization, [service], ["any"], desired_date)
    assert general[0]["items"][0]["professional"].pk == bia.pk

    # Com cliente, a escolha automática prioriza o profissional com histórico dele.
    slot = services.calcular_slots_disponiveis(
        organization, [service], ["any"], desired_date, customer=customer
    )[0]
    assert slot["items"][0]["professional"].pk == bia.pk


@pytest.mark.django_db
def test_disponibilidade_autenticada_aceita_customer_e_isola_tenant(
    auth_client, organization, other_organization
):
    _, service, _, customer, _ = make_schedule(organization)
    foreign = CustomerFactory(organization=other_organization)

    ok = auth_client.get(
        reverse("availability"),
        {
            "services": str(service.pk),
            "professional": "any",
            "date": timezone.localdate() + timedelta(days=7),
            "customer": customer.pk,
        },
    )
    assert ok.status_code == 200

    blocked = auth_client.get(
        reverse("availability"),
        {
            "services": str(service.pk),
            "professional": "any",
            "date": timezone.localdate() + timedelta(days=7),
            "customer": foreign.pk,
        },
    )
    assert blocked.status_code == 404
