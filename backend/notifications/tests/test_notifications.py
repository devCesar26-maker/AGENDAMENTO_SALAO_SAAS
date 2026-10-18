"""Cobertura de tarefas de e-mail, lembretes e lista de espera."""

from datetime import datetime, time, timedelta
from unittest.mock import patch
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
from notifications.models import NotificationEvent, WaitlistEntry
from notifications.tasks import (
    dispatch_notification_outbox,
    send_appointment_confirmation,
    send_appointment_reminders,
)
from scheduling.models import Appointment, AppointmentItem
from scheduling.services import change_appointment_status, create_appointment

WEEKDAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def make_schedule(organization, *, email="cliente@example.com"):
    desired_date = timezone.localdate() + timedelta(days=7)
    organization.timezone = "America/Sao_Paulo"
    organization.working_hours = {
        WEEKDAY_KEYS[desired_date.weekday()]: [["09:00", "18:00"]]
    }
    organization.save(update_fields=["timezone", "working_hours"])
    professional = ProfessionalFactory(organization=organization, name="Bia")
    category = ServiceCategoryFactory(organization=organization)
    service = ServiceFactory(
        organization=organization,
        category=category,
        name="Corte",
        duration_minutes=30,
        price="75.00",
    )
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
    customer = CustomerFactory(organization=organization, email=email)
    start_at = datetime.combine(
        desired_date, time(10), tzinfo=ZoneInfo(organization.timezone)
    )
    return desired_date, service, professional, customer, start_at


def create_raw_appointment(
    organization, service, professional, customer, start_at, *, status=None
):
    appointment = Appointment.objects.create(
        organization=organization,
        customer=customer,
        status=status or Appointment.Status.SCHEDULED,
    )
    AppointmentItem.objects.create(
        organization=organization,
        appointment=appointment,
        service=service,
        professional=professional,
        order=0,
        start_at=start_at,
        end_at=start_at + timedelta(minutes=service.duration_minutes),
        price=service.price,
    )
    return appointment


@pytest.mark.django_db
def test_criar_agendamento_persiste_confirmacao_no_outbox(organization):
    _, service, professional, customer, start_at = make_schedule(organization)
    mail.outbox.clear()

    appointment = create_appointment(
        organization=organization,
        customer=customer,
        items=[{"service": service, "professional": professional, "order": 0}],
        desired_start=start_at,
        membership=organization.memberships.first(),
    )

    assert appointment.pk
    event = NotificationEvent.objects.get(
        appointment=appointment, kind=NotificationEvent.Kind.CONFIRMATION
    )
    assert event.state == NotificationEvent.State.PENDING
    assert dispatch_notification_outbox.run() == 1
    event.refresh_from_db()
    assert event.state == NotificationEvent.State.SENT
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [customer.email]
    assert organization.name in mail.outbox[0].subject
    assert "Corte" in mail.outbox[0].body
    assert "Bia" in mail.outbox[0].body
    assert dispatch_notification_outbox.run() == 0
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_tarefa_de_confirmacao_repetida_envia_email_uma_unica_vez(organization):
    _, service, professional, customer, start_at = make_schedule(organization)
    appointment = create_appointment(
        organization=organization,
        customer=customer,
        items=[{"service": service, "professional": professional, "order": 0}],
        desired_start=start_at,
        membership=organization.memberships.first(),
    )
    mail.outbox.clear()

    assert send_appointment_confirmation.run(appointment.pk) is True
    assert send_appointment_confirmation.run(appointment.pk) is False
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [customer.email]
    assert organization.name in mail.outbox[0].subject
    assert "Corte" in mail.outbox[0].body
    assert "Bia" in mail.outbox[0].body
    assert dispatch_notification_outbox.run() == 1
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_outbox_reagenda_evento_apos_falha_temporaria_de_smtp(organization):
    _, service, professional, customer, start_at = make_schedule(organization)
    appointment = create_appointment(
        organization=organization,
        customer=customer,
        items=[{"service": service, "professional": professional, "order": 0}],
        desired_start=start_at,
        membership=organization.memberships.first(),
    )
    event = NotificationEvent.objects.get(
        appointment=appointment, kind=NotificationEvent.Kind.CONFIRMATION
    )

    with patch(
        "notifications.tasks.send_mail", side_effect=OSError("SMTP indisponível")
    ):
        assert dispatch_notification_outbox.run() == 0

    event.refresh_from_db()
    assert event.state == NotificationEvent.State.PENDING
    assert event.attempts == 1
    assert event.last_error == "OSError"
    assert event.available_at > timezone.now()


@pytest.mark.django_db
def test_lembretes_apenas_na_janela_sem_reenvio_e_sem_n_plus_one(
    organization, django_assert_num_queries
):
    _, service, professional, _, _ = make_schedule(organization)
    eligible = CustomerFactory(organization=organization, email="lembrete@example.com")
    confirmed = CustomerFactory(
        organization=organization, email="confirmado@example.com"
    )
    outside = CustomerFactory(organization=organization, email="fora@example.com")
    canceled = CustomerFactory(organization=organization, email="cancelado@example.com")
    already_sent = CustomerFactory(organization=organization, email="jafoi@example.com")
    now = timezone.now()
    appointment = create_raw_appointment(
        organization,
        service,
        professional,
        eligible,
        now + timedelta(hours=24),
    )
    create_raw_appointment(
        organization,
        service,
        professional,
        confirmed,
        now + timedelta(hours=24),
        status=Appointment.Status.CONFIRMED,
    )
    create_raw_appointment(
        organization, service, professional, outside, now + timedelta(hours=25)
    )
    create_raw_appointment(
        organization,
        service,
        professional,
        canceled,
        now + timedelta(hours=24),
        status=Appointment.Status.CANCELED,
    )
    sent_appointment = create_raw_appointment(
        organization,
        service,
        professional,
        already_sent,
        now + timedelta(hours=24),
    )
    sent_appointment.reminder_sent_at = now
    sent_appointment.save(update_fields=["reminder_sent_at"])
    mail.outbox.clear()

    # As consultas crescem por lote/tenant, não por agendamento individual.
    with django_assert_num_queries(9):
        assert send_appointment_reminders.run() == 2

    appointment.refresh_from_db()
    assert appointment.reminder_sent_at is not None
    assert len(mail.outbox) == 2
    assert {message.to[0] for message in mail.outbox} == {
        eligible.email,
        confirmed.email,
    }
    assert send_appointment_reminders.run() == 0
    assert len(mail.outbox) == 2


@pytest.mark.django_db
def test_cancelamento_persiste_eventos_e_avisa_entradas_compativeis(organization):
    desired_date, service, professional, customer, start_at = make_schedule(
        organization
    )
    appointment = create_raw_appointment(
        organization, service, professional, customer, start_at
    )
    other_service = ServiceFactory(organization=organization)
    other_professional = ProfessionalFactory(
        organization=organization, name="Outra pro"
    )
    compatible = WaitlistEntry.objects.create(
        organization=organization,
        customer=CustomerFactory(organization=organization, email="espera@example.com"),
        service=service,
        professional=None,
        desired_date=desired_date,
    )
    wrong_service = WaitlistEntry.objects.create(
        organization=organization,
        customer=CustomerFactory(
            organization=organization, email="outro-servico@example.com"
        ),
        service=other_service,
        desired_date=desired_date,
    )
    wrong_professional = WaitlistEntry.objects.create(
        organization=organization,
        customer=CustomerFactory(
            organization=organization, email="outra-pro@example.com"
        ),
        service=service,
        professional=other_professional,
        desired_date=desired_date,
    )
    mail.outbox.clear()

    change_appointment_status(appointment, Appointment.Status.CANCELED)
    assert NotificationEvent.objects.filter(appointment=appointment).count() == 2
    assert dispatch_notification_outbox.run() == 2

    compatible.refresh_from_db()
    wrong_service.refresh_from_db()
    wrong_professional.refresh_from_db()
    assert compatible.notified_at is not None
    assert wrong_service.notified_at is None
    assert wrong_professional.notified_at is None
    assert len(mail.outbox) == 2
    assert customer.email in mail.outbox[0].to
    assert "Horário disponível" in mail.outbox[1].subject
    assert "não fica reservado" in mail.outbox[1].body


@pytest.mark.django_db
def test_lista_de_espera_autenticada_isola_tenant_e_exige_manager(
    manager_client, organization, other_organization
):
    desired_date, service, professional, customer, _ = make_schedule(organization)
    entry = WaitlistEntry.objects.create(
        organization=organization,
        customer=customer,
        service=service,
        professional=professional,
        desired_date=desired_date,
    )
    other_date, other_service, _, other_customer, _ = make_schedule(other_organization)
    other_entry = WaitlistEntry.objects.create(
        organization=other_organization,
        customer=other_customer,
        service=other_service,
        desired_date=other_date,
    )

    response = manager_client.get(reverse("waitlist-list-create"))
    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["results"][0]["id"] == entry.pk
    assert other_entry.pk not in {row["id"] for row in response.json()["results"]}
    assert (
        manager_client.delete(
            reverse("waitlist-delete", kwargs={"pk": other_entry.pk})
        ).status_code
        == 404
    )


@pytest.mark.django_db
def test_lista_publica_cria_cliente_e_escopa_servico_ao_tenant(
    api_client, organization, other_organization
):
    desired_date, service, professional, _, _ = make_schedule(organization)
    _, foreign_service, _, _, _ = make_schedule(other_organization)
    response = api_client.post(
        reverse("public-waitlist"),
        {
            "name": "Cliente Espera",
            "phone": "+55 (11) 98888-1234",
            "email": "espera-publica@example.com",
            "consent": True,
            "service": service.pk,
            "professional": professional.pk,
            "desired_date": desired_date.isoformat(),
            "organization": other_organization.pk,
        },
        format="json",
        HTTP_X_TENANT_SLUG=organization.slug,
    )
    assert response.status_code == 201, response.json()
    entry = WaitlistEntry.objects.get(pk=response.json()["id"])
    assert entry.organization_id == organization.pk
    assert entry.service_id == service.pk
    assert entry.customer.email == "espera-publica@example.com"
    assert entry.customer.lgpd_consent is True

    foreign_response = api_client.post(
        reverse("public-waitlist"),
        {
            "name": "Cliente Estrangeiro",
            "phone": "11988881235",
            "email": "estrangeiro@example.com",
            "consent": True,
            "service": foreign_service.pk,
            "desired_date": desired_date.isoformat(),
        },
        format="json",
        HTTP_X_TENANT_SLUG=organization.slug,
    )
    assert foreign_response.status_code == 400
    assert WaitlistEntry.objects.filter(organization=other_organization).count() == 0


@pytest.mark.django_db
def test_lista_publica_nao_altera_identidade_de_cliente_existente(
    api_client, organization
):
    desired_date, service, professional, _, _ = make_schedule(organization)
    customer = CustomerFactory(
        organization=organization,
        name="Cliente conhecido",
        phone="11988880000",
        email="cliente-conhecido@example.com",
    )
    response = api_client.post(
        reverse("public-waitlist"),
        {
            "name": "Pessoa tentando se passar pelo cliente",
            "phone": customer.phone,
            "email": "atacante@example.com",
            "consent": True,
            "service": service.pk,
            "professional": professional.pk,
            "desired_date": desired_date.isoformat(),
        },
        format="json",
        HTTP_X_TENANT_SLUG=organization.slug,
    )
    customer.refresh_from_db()
    assert response.status_code == 400
    assert customer.name == "Cliente conhecido"
    assert customer.phone == "11988880000"
    assert customer.email == "cliente-conhecido@example.com"
