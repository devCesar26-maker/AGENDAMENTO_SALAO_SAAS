"""Tarefas assíncronas de sugestões preditivas e FlashSlot."""

import logging
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from celery import shared_task
from django.conf import settings
from django.db.models import Min
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from scheduling.models import Appointment, FlashSlot
from scheduling.services import SlotUnavailable

logger = logging.getLogger("ecalt")

FLASH_DISCOUNT_LADDER = (10, 20, 30)
FLASH_DAYS_AHEAD = 7
FLASH_EXPIRES_HOURS = 24
FLASH_MINIMUM_DISCOUNT = 10


def _service_signature(items):
    return tuple(sorted(item.service_id for item in items))


def _first_completed_appointments(organization):
    """Últimos atendimentos concluídos por cliente, em uma query por organização."""
    appointments = (
        Appointment.objects.filter(organization=organization, status=Appointment.Status.COMPLETED)
        .prefetch_related("items__service", "items__professional")
        .order_by("customer_id", "-items__start_at", "pk")
    )
    latest = {}
    for appointment in appointments:
        if appointment.customer_id not in latest:
            latest[appointment.customer_id] = appointment
    return latest


def _suggestion_is_duplicate(organization, customer, items):
    window_start = timezone.now() - timedelta(hours=settings.RECURRING_SUGGESTION_HOURS)
    signature = _service_signature(items)
    recent = Appointment.objects.filter(
        organization=organization,
        customer=customer,
        status=Appointment.Status.SUGGESTED,
        created_at__gte=window_start,
    ).prefetch_related("items")
    for appointment in recent:
        if _service_signature(list(appointment.items.all())) == signature:
            return True
    return False


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def generate_recurring_suggestions(organization_id, lookahead_days=14):
    """Para cada cliente com histórico, calcula o intervalo e sugere o próximo horário."""
    from organizations.models import Organization
    from scheduling import services

    organization = Organization.objects.filter(pk=organization_id, is_active=True).first()
    if organization is None:
        return 0
    tz = ZoneInfo(organization.timezone)
    today = timezone.localdate(timezone=tz)
    created = 0
    for customer_id, last in _first_completed_appointments(organization).items():
        items = list(last.items.all())
        if not items:
            continue
        completed = list(
            Appointment.objects.filter(
                organization=organization,
                customer_id=customer_id,
                status=Appointment.Status.COMPLETED,
                items__service_id__in=[item.service_id for item in items],
            )
            .annotate(first_item=Min("items__start_at"))
            .order_by("first_item")
            .distinct()
        )
        if len(completed) < 2:
            continue
        dates = sorted(
            timezone.localtime(value, tz).date()
            for value in (
                Appointment.objects.filter(
                    organization=organization,
                    customer_id=customer_id,
                    status=Appointment.Status.COMPLETED,
                )
                .annotate(first_item=Min("items__start_at"))
                .values_list("first_item", flat=True)
            )
            if value is not None
        )
        if len(dates) < 2:
            continue
        intervals = [
            (dates[index + 1] - dates[index]).days
            for index in range(len(dates) - 1)
            if (dates[index + 1] - dates[index]).days > 0
        ]
        if not intervals:
            continue
        average_interval = round(sum(intervals) / len(intervals))
        if average_interval < 7:
            continue
        expected = dates[-1] + timedelta(days=average_interval)
        if not (today <= expected <= today + timedelta(days=lookahead_days)):
            continue
        if Appointment.objects.filter(
            organization=organization,
            customer_id=customer_id,
            status__in=(
                Appointment.Status.SCHEDULED,
                Appointment.Status.CONFIRMED,
                Appointment.Status.SUGGESTED,
            ),
            items__start_at__gte=timezone.now(),
        ).exists():
            continue
        if _suggestion_is_duplicate(organization, last.customer, items):
            continue
        professional_ids = [item.professional_id for item in items]
        service_ids = [item.service_id for item in items]
        from catalog.models import Professional, Service

        service_map = {
            service.pk: service
            for service in Service.objects.filter(
                organization=organization, pk__in=service_ids, is_active=True
            )
        }
        professional_map = {
            professional.pk: professional
            for professional in Professional.objects.filter(
                organization=organization, pk__in=professional_ids, is_active=True
            )
        }
        if any(pk not in service_map for pk in service_ids) or any(
            pk not in professional_map for pk in professional_ids
        ):
            continue
        selected = None
        for offset in range(lookahead_days + 1):
            candidate_day = expected + timedelta(days=offset)
            slots = services.calcular_slots_disponiveis(
                organization,
                [service_map[pk] for pk in service_ids],
                [professional_map[pk] for pk in professional_ids],
                candidate_day,
                customer=last.customer,
                apply_flash=False,
            )
            if slots:
                selected = (candidate_day, slots[0])
                break
        if selected is None:
            continue
        expires_at = timezone.now() + timedelta(hours=settings.RECURRING_SUGGESTION_HOURS)
        appointment_items = [
            {
                "service": snapshot["service"],
                "professional": snapshot["professional"],
                "order": order,
            }
            for order, snapshot in enumerate(selected[1]["items"])
        ]
        try:
            appointment = services.create_appointment(
                organization=organization,
                customer=last.customer,
                items=appointment_items,
                desired_start=selected[1]["start_at"],
                membership=None,
                origin=Appointment.Origin.RECURRING,
                status=Appointment.Status.SUGGESTED,
                check_limit=False,
                notify=False,
                suggestion_expires_at=expires_at,
            )
        except (SlotUnavailable, ValidationError) as exc:
            logger.info("Sugestão ignorada para o cliente %s: %s", last.customer_id, exc)
            continue
        from notifications.models import NotificationEvent
        from notifications.services import queue_appointment_notification

        queue_appointment_notification(appointment, NotificationEvent.Kind.RECURRING_SUGGESTION)
        created += 1
    return created


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def generate_flash_slots(organization_id, days_ahead=FLASH_DAYS_AHEAD):
    """Gera FlashSlots para lacunas dos próximos dias, respeitando o teto do salão."""
    from organizations.models import Organization
    from scheduling import services

    organization = Organization.objects.filter(pk=organization_id, is_active=True).first()
    if organization is None:
        return 0
    tz = ZoneInfo(organization.timezone)
    cap = max(0, min(90, organization.flash_slot_max_discount_percent or 0))
    ladder = [value for value in FLASH_DISCOUNT_LADDER if value <= cap]
    if not ladder:
        return 0
    today = timezone.localdate(timezone=tz)
    created = 0
    for service in _active_services(organization):
        for professional in _service_professionals(organization, service):
            covered_days = {
                timezone.localtime(value, tz).date()
                for value in FlashSlot.objects.filter(
                    organization=organization,
                    service=service,
                    professional=professional,
                    start_at__gte=timezone.now(),
                ).values_list("start_at", flat=True)
            }
            for offset in range(1, days_ahead + 1):
                day = today + timedelta(days=offset)
                if day in covered_days:
                    continue
                slots = services.calcular_slots_disponiveis(
                    organization,
                    [service],
                    [professional],
                    day,
                    apply_flash=False,
                )
                if not slots:
                    continue
                item = slots[0]["items"][0]
                # B3: nunca criar FlashSlot para serviço gratuito (preço = 0).
                # Um desconto sobre zero resulta em discount_price = 0, o que
                # é inválido como oferta promocional.
                effective_price = item.get("price") or Decimal("0")
                if effective_price <= Decimal("0"):
                    continue
                discount = _discount_for(day, today, ladder)
                if discount < FLASH_MINIMUM_DISCOUNT:
                    continue
                expires_at = min(
                    timezone.now() + timedelta(hours=FLASH_EXPIRES_HOURS),
                    item["start_at"],
                )
                if expires_at <= timezone.now():
                    continue
                FlashSlot.objects.create(
                    organization=organization,
                    service=service,
                    professional=professional,
                    start_at=item["start_at"],
                    end_at=item["end_at"],
                    original_price=item["price"],
                    discount_percent=discount,
                    expires_at=expires_at,
                )
                created += 1
    return created


def _discount_for(day, today, ladder):
    """Degraus crescentes conforme a vaga se aproxima, sempre dentro do teto do salão."""
    distance = (day - today).days
    index = 0 if distance >= 5 else 1 if distance >= 3 else 2
    index = min(index, len(ladder) - 1)
    return ladder[index]


def _active_services(organization):
    from catalog.models import Service

    return list(Service.objects.filter(organization=organization, is_active=True)[:200])


def _service_professionals(organization, service):
    from catalog.models import Professional

    return list(
        Professional.objects.filter(
            organization=organization,
            is_active=True,
            service_links__service=service,
        ).distinct()[:50]
    )


@shared_task
def generate_flash_slots_for_active_organizations():
    from organizations.models import Organization

    total = 0
    for organization_id in Organization.objects.filter(is_active=True).values_list("pk", flat=True):
        total += generate_flash_slots.run(organization_id)
    return total


@shared_task
def generate_recurring_suggestions_for_active_organizations():
    from organizations.models import Organization

    total = 0
    for organization_id in Organization.objects.filter(is_active=True).values_list("pk", flat=True):
        total += generate_recurring_suggestions.run(organization_id)
    return total


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def refresh_flash_slot_prices(batch_size=200):
    """Recalcula degraus de desconto de FlashSlots ativos conforme a proximidade."""
    now = timezone.now()
    slots = list(
        FlashSlot.objects.filter(
            status=FlashSlot.Status.ACTIVE, expires_at__gt=now, start_at__gt=now
        )
        .select_related("organization")
        .order_by("start_at")[:batch_size]
    )
    updated = 0
    for slot in slots:
        tz = ZoneInfo(slot.organization.timezone)
        today = timezone.localdate(timezone=tz)
        cap = max(0, min(90, slot.organization.flash_slot_max_discount_percent or 0))
        ladder = [value for value in FLASH_DISCOUNT_LADDER if value <= cap]
        if not ladder or slot.original_price <= Decimal("0"):
            slot.status = FlashSlot.Status.EXPIRED
            slot.save(update_fields=["status", "updated_at"])
            continue
        day = timezone.localtime(slot.start_at, tz).date()
        discount = _discount_for(day, today, ladder)
        if discount == slot.discount_percent:
            continue
        slot.discount_percent = discount
        slot.save(update_fields=["discount_percent", "discount_price", "updated_at"])
        updated += 1
    return updated


@shared_task
def expire_flash_slots(batch_size=500):
    now = timezone.now()
    expired = FlashSlot.objects.filter(status=FlashSlot.Status.ACTIVE, expires_at__lte=now).update(
        status=FlashSlot.Status.EXPIRED
    )
    return expired
