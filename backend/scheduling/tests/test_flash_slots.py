"""FlashSlot: geração, degraus de desconto, destaque público e snapshot (item 6)."""

from datetime import time, timedelta
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
from scheduling import services
from scheduling.models import FlashSlot
from scheduling.tasks import (
    expire_flash_slots,
    generate_flash_slots,
    refresh_flash_slot_prices,
)

WEEKDAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def make_schedule(organization, *, max_discount=30):
    organization.timezone = "America/Sao_Paulo"
    organization.flash_slot_max_discount_percent = max_discount
    organization.working_hours = {key: [["09:00", "18:00"]] for key in WEEKDAY_KEYS}
    organization.save(
        update_fields=["timezone", "working_hours", "flash_slot_max_discount_percent"]
    )
    category = ServiceCategoryFactory(organization=organization)
    service = ServiceFactory(
        organization=organization,
        category=category,
        name="Corte",
        duration_minutes=30,
        price="100.00",
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
    customer = CustomerFactory(organization=organization)
    return service, professional, customer


@pytest.mark.django_db
def test_gera_flash_slots_com_degraus_dentro_do_teto(organization):
    _, _, _ = make_schedule(organization, max_discount=20)

    created = generate_flash_slots.run(organization.pk)
    assert created > 0

    slots = FlashSlot.objects.filter(organization=organization, status=FlashSlot.Status.ACTIVE)
    assert slots.exists()
    assert all(slot.discount_percent <= 20 for slot in slots)
    assert all(slot.discount_percent in {10, 20} for slot in slots)
    sample = slots.first()
    assert sample.original_price == Decimal("100.00")
    expected = (Decimal("100.00") * Decimal(100 - sample.discount_percent) / 100).quantize(
        Decimal("0.01")
    )
    assert sample.discount_price == expected


@pytest.mark.django_db
def test_teto_zero_nao_cria_desconto(organization):
    make_schedule(organization, max_discount=0)
    assert generate_flash_slots.run(organization.pk) == 0
    assert not FlashSlot.objects.exists()


@pytest.mark.django_db
def test_geracao_e_idempotente_no_mesmo_slot(organization):
    make_schedule(organization)
    generate_flash_slots.run(organization.pk)
    count = FlashSlot.objects.count()
    generate_flash_slots.run(organization.pk)
    assert FlashSlot.objects.count() == count


@pytest.mark.django_db
def test_disponibilidade_publica_destaca_preco_com_desconto(organization):
    service, professional, _ = make_schedule(organization)
    generate_flash_slots.run(organization.pk)
    slot = FlashSlot.objects.filter(status=FlashSlot.Status.ACTIVE).first()
    tz = ZoneInfo(organization.timezone)
    day = timezone.localtime(slot.start_at, tz).date()

    slots = services.calcular_slots_disponiveis(organization, [service], [professional], day)
    discounted = [item for item in slots if item["start_at"] == slot.start_at]
    assert discounted
    item = discounted[0]["items"][0]
    assert item["discount_percent"] == slot.discount_percent
    assert item["price"] == slot.discount_price
    assert item["flash_slot"].pk == slot.pk


@pytest.mark.django_db
def test_reserva_congela_preco_com_desconto_e_marca_slot(organization):
    service, professional, customer = make_schedule(organization)
    generate_flash_slots.run(organization.pk)
    slot = FlashSlot.objects.filter(status=FlashSlot.Status.ACTIVE).first()

    appointment = services.create_appointment(
        organization=organization,
        customer=customer,
        items=[{"service": service, "professional": professional, "order": 0}],
        desired_start=slot.start_at,
        membership=None,
    )
    item = appointment.items.get()
    assert item.price == slot.discount_price
    assert item.discount_percent == slot.discount_percent
    assert item.flash_slot_id == slot.pk
    slot.refresh_from_db()
    assert slot.status == FlashSlot.Status.BOOKED


@pytest.mark.django_db
def test_recalculo_aumenta_desconto_conforme_aproxima(organization):
    make_schedule(organization)
    generate_flash_slots.run(organization.pk)
    slot = FlashSlot.objects.filter(status=FlashSlot.Status.ACTIVE).first()
    FlashSlot.objects.filter(pk=slot.pk).update(discount_percent=10)
    # Move a vaga para muito perto, forçando o degrau mais alto.
    FlashSlot.objects.filter(pk=slot.pk).update(
        start_at=timezone.now() + timedelta(hours=20),
        expires_at=timezone.now() + timedelta(hours=19),
    )

    refresh_flash_slot_prices.run()
    slot.refresh_from_db()
    assert slot.discount_percent == 30


@pytest.mark.django_db
def test_expiracao_marca_slots_vencidos(organization):
    make_schedule(organization)
    generate_flash_slots.run(organization.pk)
    FlashSlot.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
    assert expire_flash_slots.run() == FlashSlot.objects.count()
    assert not FlashSlot.objects.filter(status=FlashSlot.Status.ACTIVE).exists()


@pytest.mark.django_db
def test_availability_publica_rejeita_tenant_sem_cabecalho(api_client, organization):
    service, _, _ = make_schedule(organization)
    generate_flash_slots.run(organization.pk)
    slot = FlashSlot.objects.filter(status=FlashSlot.Status.ACTIVE).first()
    tz = ZoneInfo(organization.timezone)
    day = timezone.localtime(slot.start_at, tz).date()

    response = api_client.get(
        reverse("public-availability"),
        {"services": str(service.pk), "professional": "any", "date": day.isoformat()},
    )
    # Sem X-Tenant-Slug o middleware não resolve o salão e bloqueia.
    assert response.status_code == 404

    response = api_client.get(
        reverse("public-availability"),
        {"services": str(service.pk), "professional": "any", "date": day.isoformat()},
        HTTP_X_TENANT_SLUG=organization.slug,
    )
    assert response.status_code == 200
    payload = response.json()["slots"]
    assert any(
        item["discount_percent"] == slot.discount_percent
        for slot_payload in payload
        for item in slot_payload["items"]
    )
