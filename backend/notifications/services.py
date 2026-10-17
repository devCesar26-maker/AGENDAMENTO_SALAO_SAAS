"""Regras de domínio para lista de espera."""

from zoneinfo import ZoneInfo

from django.db.models import Q
from django.utils import timezone

from notifications.models import NotificationEvent, WaitlistEntry


def queue_appointment_notification(appointment, kind):
    """Persiste o evento na mesma transação da alteração de agendamento."""
    return NotificationEvent.objects.get_or_create(
        organization=appointment.organization,
        appointment=appointment,
        kind=kind,
    )[0]


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
