"""Sugestões preditivas de recorrência: criação, confirmação, recusa e expiração (item 5)."""

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
from notifications.tasks import dispatch_notification_outbox, expire_suggested_appointments
from scheduling import services
from scheduling.models import Appointment, AppointmentToken
from scheduling.tasks import generate_recurring_suggestions

WEEKDAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def make_schedule(organization):
    organization.timezone = "America/Sao_Paulo"
    organization.working_hours = {key: [["09:00", "18:00"]] for key in WEEKDAY_KEYS}
    organization.save(update_fields=["timezone", "working_hours"])
    category = ServiceCategoryFactory(organization=organization)
    service = ServiceFactory(
        organization=organization,
        category=category,
        name="Corte",
        duration_minutes=30,
        price="75.00",
    )
    professional = ProfessionalFactory(organization=organization, name="Ana")
    ProfessionalServiceFactory(
        organization=organization, professional=professional, service=service
    )
    for weekday in range(7):
        WorkingHoursFactory(
            organization=organization,
            professional=professional,
            weekday=weekday,
            start_time=time(9, 0),
            end_time=time(18, 0),
        )
    customer = CustomerFactory(organization=organization, email="cliente@example.com")
    return service, professional, customer


def complete_visit(organization, service, professional, customer, days_ago):
    tz = ZoneInfo(organization.timezone)
    start_at = datetime.combine(
        timezone.localdate(timezone=tz) - timedelta(days=days_ago), time(10), tzinfo=tz
    )
    appointment = Appointment.objects.create(
        organization=organization, customer=customer, status=Appointment.Status.COMPLETED
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
    return appointment


@pytest.mark.django_db
def test_gera_sugestao_quando_intervalo_medio_vence(organization):
    service, professional, customer = make_schedule(organization)
    complete_visit(organization, service, professional, customer, days_ago=42)
    complete_visit(organization, service, professional, customer, days_ago=14)

    created = generate_recurring_suggestions.run(organization.pk)
    assert created == 1

    suggestion = Appointment.objects.get(status=Appointment.Status.SUGGESTED)
    assert suggestion.origin == Appointment.Origin.RECURRING
    assert suggestion.suggestion_expires_at > timezone.now()
    assert suggestion.items.count() == 1
    event = NotificationEvent.objects.get(
        appointment=suggestion, kind=NotificationEvent.Kind.RECURRING_SUGGESTION
    )
    assert event.waitlist_offer_id is None

    mail.outbox.clear()
    assert dispatch_notification_outbox.run() == 1
    token = AppointmentToken.objects.get(
        appointment=suggestion, action=AppointmentToken.Action.CONFIRM
    )
    assert f"/sugestao/{token.token}" in mail.outbox[0].body


@pytest.mark.django_db
def test_nao_gera_sugestao_se_tem_agendamento_futuro(organization):
    service, professional, customer = make_schedule(organization)
    complete_visit(organization, service, professional, customer, days_ago=42)
    complete_visit(organization, service, professional, customer, days_ago=14)
    future = timezone.now() + timedelta(days=3)
    appointment = Appointment.objects.create(
        organization=organization, customer=customer, status=Appointment.Status.SCHEDULED
    )
    appointment.items.create(
        organization=organization,
        service=service,
        professional=professional,
        order=0,
        start_at=future,
        end_at=future + timedelta(minutes=30),
        price=service.price,
    )

    assert generate_recurring_suggestions.run(organization.pk) == 0


@pytest.mark.django_db
def test_sugestao_nao_bloqueia_o_slot_enquanto_pendente(organization):
    """B1: horario sugerido deve continuar disponivel para outros clientes."""
    service, professional, customer = make_schedule(organization)
    complete_visit(organization, service, professional, customer, days_ago=42)
    complete_visit(organization, service, professional, customer, days_ago=14)
    generate_recurring_suggestions.run(organization.pk)
    suggestion = Appointment.objects.get(status=Appointment.Status.SUGGESTED)
    item = suggestion.items.get()
    tz = ZoneInfo(organization.timezone)
    day = timezone.localtime(item.start_at, tz).date()

    slots = services.calcular_slots_disponiveis(organization, [service], [professional], day)
    # O slot sugerido DEVE aparecer disponivel para outros clientes.
    assert any(
        slot["start_at"] == item.start_at for slot in slots
    ), "Slot sugerido nao deve bloquear a agenda antes da confirmacao."


@pytest.mark.django_db
def test_confirmar_sugestao_retorna_409_se_slot_ocupado(api_client, organization):
    """B1: confirmacao com double-booking deve retornar 409 via revalidacao."""
    service, professional, customer = make_schedule(organization)
    complete_visit(organization, service, professional, customer, days_ago=42)
    complete_visit(organization, service, professional, customer, days_ago=14)
    generate_recurring_suggestions.run(organization.pk)
    suggestion = Appointment.objects.get(status=Appointment.Status.SUGGESTED)
    item = suggestion.items.get()
    token = services.ensure_appointment_token(
        suggestion, AppointmentToken.Action.CONFIRM, expires_at=suggestion.suggestion_expires_at
    )

    # Outro cliente reserva o mesmo slot antes da confirmacao.
    other_customer = CustomerFactory(organization=organization, email="outro@example.com")
    other_appt = Appointment.objects.create(
        organization=organization, customer=other_customer, status=Appointment.Status.SCHEDULED
    )
    other_appt.items.create(
        organization=organization,
        service=service,
        professional=professional,
        order=0,
        start_at=item.start_at,
        end_at=item.end_at,
        price=service.price,
    )

    response = api_client.post(
        reverse("public-suggestion-decision", args=[token.token, "confirm"]),
        format="json",
    )
    assert response.status_code == 409, response.json()
    suggestion.refresh_from_db()
    assert suggestion.status == Appointment.Status.SUGGESTED


@pytest.mark.django_db
def test_confirmar_sugestao_publica_confirma_e_consome_token(api_client, organization):
    service, professional, customer = make_schedule(organization)
    complete_visit(organization, service, professional, customer, days_ago=42)
    complete_visit(organization, service, professional, customer, days_ago=14)
    generate_recurring_suggestions.run(organization.pk)
    suggestion = Appointment.objects.get(status=Appointment.Status.SUGGESTED)
    token = services.ensure_appointment_token(
        suggestion, AppointmentToken.Action.CONFIRM, expires_at=suggestion.suggestion_expires_at
    )

    response = api_client.get(reverse("public-suggestion", args=[token.token]))
    assert response.status_code == 200

    response = api_client.post(
        reverse("public-suggestion-decision", args=[token.token, "confirm"]),
        format="json",
    )
    assert response.status_code == 200
    suggestion.refresh_from_db()
    assert suggestion.status == Appointment.Status.CONFIRMED
    assert suggestion.suggestion_expires_at is None
    token.refresh_from_db()
    assert token.used_at is not None
    assert NotificationEvent.objects.filter(
        appointment=suggestion, kind=NotificationEvent.Kind.CONFIRMATION
    ).exists()


@pytest.mark.django_db
def test_recusar_sugestao_publica_cancela_sem_email_de_cancelamento(api_client, organization):
    service, professional, customer = make_schedule(organization)
    complete_visit(organization, service, professional, customer, days_ago=42)
    complete_visit(organization, service, professional, customer, days_ago=14)
    generate_recurring_suggestions.run(organization.pk)
    suggestion = Appointment.objects.get(status=Appointment.Status.SUGGESTED)
    token = services.ensure_appointment_token(
        suggestion, AppointmentToken.Action.CONFIRM, expires_at=suggestion.suggestion_expires_at
    )
    mail.outbox.clear()

    response = api_client.post(
        reverse("public-suggestion-decision", args=[token.token, "decline"]),
        format="json",
    )
    assert response.status_code == 200
    suggestion.refresh_from_db()
    assert suggestion.status == Appointment.Status.CANCELED
    assert not NotificationEvent.objects.filter(
        appointment=suggestion, kind=NotificationEvent.Kind.CANCELLATION
    ).exists()


@pytest.mark.django_db
def test_expiracao_cancela_sugestoes_vencidas(organization):
    service, professional, customer = make_schedule(organization)
    complete_visit(organization, service, professional, customer, days_ago=42)
    complete_visit(organization, service, professional, customer, days_ago=14)
    generate_recurring_suggestions.run(organization.pk)
    suggestion = Appointment.objects.get(status=Appointment.Status.SUGGESTED)
    Appointment.objects.filter(pk=suggestion.pk).update(
        suggestion_expires_at=timezone.now() - timedelta(minutes=1)
    )

    assert expire_suggested_appointments.run() == 1
    suggestion.refresh_from_db()
    assert suggestion.status == Appointment.Status.CANCELED
    assert suggestion.suggestion_expires_at is None


@pytest.mark.django_db
def test_token_de_sugestao_nao_serve_para_rating(api_client, organization):
    service, professional, customer = make_schedule(organization)
    complete_visit(organization, service, professional, customer, days_ago=42)
    complete_visit(organization, service, professional, customer, days_ago=14)
    generate_recurring_suggestions.run(organization.pk)
    suggestion = Appointment.objects.get(status=Appointment.Status.SUGGESTED)
    token = services.ensure_appointment_token(
        suggestion, AppointmentToken.Action.CONFIRM, expires_at=suggestion.suggestion_expires_at
    )
    assert api_client.get(reverse("public-rating", args=[token.token])).status_code == 404
