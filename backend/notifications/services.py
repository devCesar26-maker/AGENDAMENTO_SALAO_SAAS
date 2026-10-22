"""Regras de domínio para lista de espera."""

from datetime import timedelta
from zoneinfo import ZoneInfo

from django.db.models import Q
from django.utils import timezone

from notifications.models import NotificationEvent, WaitlistEntry, WaitlistOffer


def queue_appointment_notification(appointment, kind, *, waitlist_offer=None):
    """Persiste o evento na mesma transação da alteração de agendamento."""
    return NotificationEvent.objects.get_or_create(
        organization=appointment.organization,
        appointment=appointment,
        kind=kind,
        waitlist_offer=waitlist_offer,
    )[0]


def _priority_candidates(item):
    tz = ZoneInfo(item.organization.timezone)
    desired_date = timezone.localtime(item.start_at, tz).date()
    return (
        WaitlistEntry.objects.filter(
            organization=item.organization,
            service_id=item.service_id,
            desired_date=desired_date,
            notified_at__isnull=True,
            converted_at__isnull=True,
            customer__email__gt="",
        )
        .filter(Q(professional__isnull=True) | Q(professional_id=item.professional_id))
        .select_related("customer", "service", "professional")
        .order_by("created_at")
    )


def _create_priority_offer(entry, item):
    appointment = item.appointment
    window = max(1, min(60, appointment.organization.waitlist_priority_window_minutes or 10))
    offer = WaitlistOffer.objects.create(
        organization=appointment.organization,
        entry=entry,
        appointment_item=item,
        expires_at=timezone.now() + timedelta(minutes=window),
    )
    WaitlistEntry.objects.filter(pk=entry.pk, notified_at__isnull=True).update(
        notified_at=timezone.now()
    )
    queue_appointment_notification(
        appointment, NotificationEvent.Kind.WAITLIST_PRIORITY, waitlist_offer=offer
    )
    return offer


def start_waitlist_priority_for_appointment(appointment):
    """Oferta o item compatível ao primeiro da fila (FIFO), com hold exclusivo."""
    if appointment.status != appointment.Status.CANCELED:
        return None
    items = list(
        appointment.items.select_related("service", "professional")
        .select_related("organization")
        .order_by("order")
    )
    if not items:
        return None
    existing = (
        WaitlistOffer.objects.filter(
            organization=appointment.organization,
            appointment_item__appointment=appointment,
            status=WaitlistOffer.Status.ACTIVE,
            expires_at__gt=timezone.now(),
        )
        .select_related("entry")
        .first()
    )
    if existing is not None:
        return existing
    candidates = []
    for item in items:
        candidates.extend(_priority_candidates(item))
    candidates.sort(key=lambda entry: (entry.created_at, entry.pk))
    for entry in candidates:
        matching_item = next(
            (
                item
                for item in items
                if item.service_id == entry.service_id
                and (entry.professional_id is None or entry.professional_id == item.professional_id)
            ),
            None,
        )
        if matching_item is not None:
            return _create_priority_offer(entry, matching_item)
    return None


def offer_next_waitlist_entry_for_item(item):
    """Após expiração, oferece o mesmo item ao próximo da fila, se houver."""
    if WaitlistOffer.objects.filter(
        appointment_item=item,
        status=WaitlistOffer.Status.ACTIVE,
        expires_at__gt=timezone.now(),
    ).exists():
        return None
    entry = _priority_candidates(item).first()
    if entry is None:
        return None
    return _create_priority_offer(entry, item)


def mark_waitlist_entries_converted(appointment):
    """Marca entradas do próprio cliente quando ele agenda serviço/data compatíveis."""
    tz = ZoneInfo(appointment.organization.timezone)
    compatibility = Q()
    for item in appointment.items.select_related("professional"):
        desired_date = timezone.localtime(item.start_at, tz).date()
        compatibility |= Q(service_id=item.service_id, desired_date=desired_date) & (
            Q(professional__isnull=True) | Q(professional_id=item.professional_id)
        )
    if compatibility:
        WaitlistEntry.objects.filter(
            organization=appointment.organization,
            customer=appointment.customer,
            converted_at__isnull=True,
        ).filter(compatibility).update(converted_at=timezone.now())
