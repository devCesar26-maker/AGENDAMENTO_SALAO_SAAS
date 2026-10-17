"""Consultas otimizadas do domínio de notificações."""

from zoneinfo import ZoneInfo

from django.db.models import Prefetch, Q
from django.utils import timezone

from notifications.models import WaitlistEntry
from scheduling.models import Appointment, AppointmentItem


def appointment_for_notification(appointment_id):
    return (
        Appointment.objects.select_related("organization", "customer")
        .prefetch_related(
            Prefetch(
                "items",
                queryset=AppointmentItem.objects.select_related("service", "professional").order_by(
                    "order"
                ),
            )
        )
        .filter(pk=appointment_id)
        .first()
    )


def reminder_candidates(window_start, window_end):
    return (
        Appointment.objects.select_related("organization", "customer")
        .prefetch_related(
            Prefetch(
                "items",
                queryset=AppointmentItem.objects.select_related("service", "professional").order_by(
                    "order"
                ),
            )
        )
        .filter(
            status__in=[Appointment.Status.SCHEDULED, Appointment.Status.CONFIRMED],
            reminder_sent_at__isnull=True,
            customer__email__gt="",
            items__start_at__range=(window_start, window_end),
        )
        .distinct()
    )


def waitlist_matches_for_open_slot(appointment, service_items):
    tz = ZoneInfo(appointment.organization.timezone)
    compatibility = Q()
    for item in service_items:
        local_date = timezone.localtime(item.start_at, tz).date()
        compatibility |= Q(service_id=item.service_id, desired_date=local_date) & (
            Q(professional__isnull=True) | Q(professional_id=item.professional_id)
        )
    if not service_items:
        return WaitlistEntry.objects.none()
    return (
        WaitlistEntry.objects.filter(
            organization=appointment.organization,
            notified_at__isnull=True,
            converted_at__isnull=True,
            customer__email__gt="",
        )
        .filter(compatibility)
        .select_related("organization", "customer", "service", "professional")
    )


def list_waitlist_entries(organization):
    return (
        WaitlistEntry.objects.filter(organization=organization)
        .select_related("customer", "service", "professional")
        .order_by("created_at")
    )
