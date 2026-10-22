"""Prioridade FIFO e hold exclusivo de vagas liberadas (item 1)."""

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
from notifications.models import WaitlistEntry, WaitlistOffer
from notifications.services import offer_next_waitlist_entry_for_item
from notifications.tasks import dispatch_notification_outbox, expire_waitlist_offers
from scheduling import services
from scheduling.models import Appointment

WEEKDAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def make_schedule(organization, *, email="cliente@example.com"):
    desired_date = timezone.localdate() + timedelta(days=7)
    organization.timezone = "America/Sao_Paulo"
    organization.working_hours = {WEEKDAY_KEYS[desired_date.weekday()]: [["09:00", "18:00"]]}
    organization.waitlist_priority_window_minutes = 10
    organization.save(
        update_fields=["timezone", "working_hours", "waitlist_priority_window_minutes"]
    )
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
    start_at = datetime.combine(desired_date, time(10), tzinfo=ZoneInfo(organization.timezone))
    return desired_date, service, professional, customer, start_at


def create_raw_appointment(organization, service, professional, customer, start_at):
    appointment = Appointment.objects.create(
        organization=organization, customer=customer, status=Appointment.Status.SCHEDULED
    )
    appointment.items.create(
        organization=organization,
        service=service,
        professional=professional,
        order=0,
        start_at=start_at,
        end_at=start_at + timedelta(minutes=service.duration_minutes),
        price=service.price,
    )
    return appointment


def add_entry(organization, service, desired_date, *, professional=None, email):
    return WaitlistEntry.objects.create(
        organization=organization,
        customer=CustomerFactory(organization=organization, email=email),
        service=service,
        professional=professional,
        desired_date=desired_date,
    )


@pytest.mark.django_db
def test_cancelamento_oferta_primeira_entrada_fifo(organization):
    desired_date, service, professional, customer, start_at = make_schedule(organization)
    appointment = create_raw_appointment(organization, service, professional, customer, start_at)
    first = add_entry(organization, service, desired_date, email="primeiro@example.com")
    second = add_entry(organization, service, desired_date, email="segundo@example.com")
    mail.outbox.clear()

    services.change_appointment_status(appointment, Appointment.Status.CANCELED)
    assert dispatch_notification_outbox.run() == 2

    first.refresh_from_db()
    second.refresh_from_db()
    assert first.notified_at is not None
    assert second.notified_at is None
    assert first.priority_offers.count() == 1
    assert second.priority_offers.count() == 0
    assert mail.outbox[1].to == ["primeiro@example.com"]


@pytest.mark.django_db
def test_hold_exclusivo_bloqueia_slot_no_motor(organization):
    desired_date, service, professional, customer, start_at = make_schedule(organization)
    appointment = create_raw_appointment(organization, service, professional, customer, start_at)
    add_entry(organization, service, desired_date, email="detentor@example.com")
    services.change_appointment_status(appointment, Appointment.Status.CANCELED)
    offer = WaitlistOffer.objects.get(status=WaitlistOffer.Status.ACTIVE)

    slots = services.calcular_slots_disponiveis(
        organization, [service], [professional], desired_date
    )
    assert all(slot["start_at"] != start_at for slot in slots)

    # Somente o detentor do token enxerga o horário com o hold ignorado.
    own = services.calcular_slots_disponiveis(
        organization,
        [service],
        [professional],
        desired_date,
        ignore_waitlist_offer_id=offer.pk,
    )
    assert any(slot["start_at"] == start_at for slot in own)


@pytest.mark.django_db
def test_expiracao_libera_para_proxima_entrada(organization):
    desired_date, service, professional, customer, start_at = make_schedule(organization)
    appointment = create_raw_appointment(organization, service, professional, customer, start_at)
    first = add_entry(organization, service, desired_date, email="primeiro@example.com")
    second = add_entry(organization, service, desired_date, email="segundo@example.com")
    services.change_appointment_status(appointment, Appointment.Status.CANCELED)
    offer = WaitlistOffer.objects.get(status=WaitlistOffer.Status.ACTIVE)
    WaitlistOffer.objects.filter(pk=offer.pk).update(
        expires_at=timezone.now() - timedelta(minutes=1)
    )

    assert expire_waitlist_offers.run() == 1

    offer.refresh_from_db()
    first.refresh_from_db()
    second.refresh_from_db()
    assert offer.status == WaitlistOffer.Status.EXPIRED
    assert second.notified_at is not None
    new_offer = WaitlistOffer.objects.get(status=WaitlistOffer.Status.ACTIVE)
    assert new_offer.entry_id == second.pk


@pytest.mark.django_db
def test_offer_next_ignora_entrada_ja_notificada(organization):
    desired_date, service, professional, customer, start_at = make_schedule(organization)
    appointment = create_raw_appointment(organization, service, professional, customer, start_at)
    first = add_entry(organization, service, desired_date, email="primeiro@example.com")
    second = add_entry(organization, service, desired_date, email="segundo@example.com")
    services.change_appointment_status(appointment, Appointment.Status.CANCELED)
    offer = WaitlistOffer.objects.get(status=WaitlistOffer.Status.ACTIVE)
    offer.status = WaitlistOffer.Status.EXPIRED
    offer.save(update_fields=["status", "updated_at"])

    next_offer = offer_next_waitlist_entry_for_item(offer.appointment_item)
    assert next_offer is not None
    assert next_offer.entry_id == second.pk
    assert next_offer.entry_id != first.pk


@pytest.mark.django_db
def test_link_prioritario_isola_tenant_e_permite_reservar(
    api_client, organization, other_organization
):
    desired_date, service, professional, customer, start_at = make_schedule(organization)
    appointment = create_raw_appointment(organization, service, professional, customer, start_at)
    entry = add_entry(organization, service, desired_date, email="detentor@example.com")
    services.change_appointment_status(appointment, Appointment.Status.CANCELED)
    offer = WaitlistOffer.objects.filter(entry=entry).get()

    # Token de outro salão não vaza: não existe no tenant A.
    response = api_client.get(reverse("public-waitlist-offer", args=[offer.token]))
    assert response.status_code == 200
    body = response.json()
    assert body["organization_name"] == organization.name
    assert body["customer_name"] == entry.customer.name

    response = api_client.post(
        reverse("public-waitlist-offer", args=[offer.token]),
        data={"consent": True},
        format="json",
    )
    assert response.status_code == 201
    created = Appointment.objects.get(pk=response.json()["id"])
    assert created.customer_id == entry.customer_id
    assert created.origin == Appointment.Origin.PUBLIC_PAGE
    assert created.items.count() == 1
    offer.refresh_from_db()
    assert offer.status == WaitlistOffer.Status.CONVERTED
    assert offer.converted_appointment_id == created.pk


@pytest.mark.django_db
def test_link_prioritario_rejeita_quando_item_ocupado(api_client, organization):
    desired_date, service, professional, customer, start_at = make_schedule(organization)
    appointment = create_raw_appointment(organization, service, professional, customer, start_at)
    entry = add_entry(organization, service, desired_date, email="detentor@example.com")
    services.change_appointment_status(appointment, Appointment.Status.CANCELED)
    offer = WaitlistOffer.objects.filter(entry=entry).get()
    # Outro cliente ocupa o horário ofertado antes do clique.
    blocker = CustomerFactory(organization=organization)
    create_raw_appointment(organization, service, professional, blocker, start_at)

    response = api_client.post(
        reverse("public-waitlist-offer", args=[offer.token]),
        data={"consent": True},
        format="json",
    )
    assert response.status_code == 409
    offer.refresh_from_db()
    assert offer.status == WaitlistOffer.Status.ACTIVE


@pytest.mark.django_db
def test_link_prioritario_expirado_retorna_410(api_client, organization):
    desired_date, service, professional, customer, start_at = make_schedule(organization)
    appointment = create_raw_appointment(organization, service, professional, customer, start_at)
    entry = add_entry(organization, service, desired_date, email="detentor@example.com")
    services.change_appointment_status(appointment, Appointment.Status.CANCELED)
    offer = WaitlistOffer.objects.filter(entry=entry).get()
    WaitlistOffer.objects.filter(pk=offer.pk).update(
        expires_at=timezone.now() - timedelta(minutes=1)
    )

    response = api_client.get(reverse("public-waitlist-offer", args=[offer.token]))
    assert response.status_code == 410


@pytest.mark.django_db
def test_oferece_apenas_primeiro_item_compativel_multisservico(organization):
    desired_date, service, professional, customer, start_at = make_schedule(organization)
    other_service = ServiceFactory(
        organization=organization, category=ServiceCategoryFactory(organization=organization)
    )
    ProfessionalServiceFactory(
        organization=organization, professional=professional, service=other_service
    )
    appointment = Appointment.objects.create(
        organization=organization, customer=customer, status=Appointment.Status.SCHEDULED
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
    appointment.items.create(
        organization=organization,
        service=other_service,
        professional=professional,
        order=1,
        start_at=start_at + timedelta(minutes=30),
        end_at=start_at + timedelta(minutes=60),
        price=other_service.price,
    )
    entry = add_entry(organization, service, desired_date, email="primeiro@example.com")
    other_entry = add_entry(organization, other_service, desired_date, email="outro@example.com")

    services.change_appointment_status(appointment, Appointment.Status.CANCELED)

    active_offers = list(WaitlistOffer.objects.filter(status=WaitlistOffer.Status.ACTIVE))
    # Oferta cobre apenas o item compatível com a entrada mais antiga (FIFO).
    assert len(active_offers) == 1
    assert active_offers[0].entry_id == entry.pk
    assert active_offers[0].appointment_item.service_id == service.pk
    other_entry.refresh_from_db()
    assert other_entry.notified_at is None
