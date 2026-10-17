"""Consultas otimizadas para disponibilidade e leitura de agendamentos."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Prefetch
from django.utils import timezone

from catalog.models import ProfessionalService
from scheduling.models import Appointment, AppointmentItem


def load_availability_data(
    organization, services, date, window_start, window_end, *, exclude_appointment_id=None
):
    """Carrega em lote vínculos, horários, folgas e ocupações para um cálculo."""
    from catalog.models import TimeOff, WorkingHours

    service_ids = [service.pk for service in services]
    links = list(
        ProfessionalService.objects.filter(
            organization=organization,
            service_id__in=service_ids,
            service__is_active=True,
            professional__is_active=True,
        ).select_related("professional", "service")
    )
    professional_ids = {link.professional_id for link in links}
    hours = list(
        WorkingHours.objects.filter(organization=organization, professional_id__in=professional_ids)
    )
    first_date = window_start.date()
    last_date = window_end.date()
    time_offs = list(
        TimeOff.objects.filter(
            organization=organization,
            professional_id__in=professional_ids,
            start_date__lte=last_date,
            end_date__gte=first_date,
        )
    )
    busy_queryset = AppointmentItem.objects.filter(
        organization=organization,
        professional_id__in=professional_ids,
        start_at__lt=window_end,
        end_at__gt=window_start - timedelta(days=2),
        appointment__status__in=[Appointment.Status.SCHEDULED, Appointment.Status.CONFIRMED],
    ).select_related("service", "appointment")
    if exclude_appointment_id is not None:
        busy_queryset = busy_queryset.exclude(appointment_id=exclude_appointment_id)
    busy_items = list(busy_queryset)
    return links, hours, time_offs, busy_items


def list_appointments(organization, *, date=None, professional=None, status=None, customer=None):
    queryset = (
        Appointment.objects.filter(organization=organization)
        .select_related("customer", "created_by__user")
        .prefetch_related(
            Prefetch(
                "items",
                queryset=AppointmentItem.objects.select_related(
                    "service", "professional", "professional__user"
                ).order_by("order"),
            )
        )
    )
    if date:
        from datetime import date as Date

        if isinstance(date, str):
            date = Date.fromisoformat(date)
        tz = ZoneInfo(organization.timezone)
        start = timezone.make_aware(datetime.combine(date, time.min), tz).astimezone(UTC)
        end = timezone.make_aware(
            datetime.combine(date + timedelta(days=1), time.min), tz
        ).astimezone(UTC)
        queryset = queryset.filter(items__start_at__gte=start, items__start_at__lt=end)
    if professional:
        queryset = queryset.filter(items__professional_id=professional)
    if status:
        queryset = queryset.filter(status=status)
    if customer:
        queryset = queryset.filter(customer_id=customer)
    return queryset.distinct().order_by("-created_at")


def get_appointment(organization, pk):
    return (
        Appointment.objects.filter(organization=organization, pk=pk)
        .select_related("customer", "created_by__user")
        .prefetch_related(
            Prefetch(
                "items",
                queryset=AppointmentItem.objects.select_related("service", "professional").order_by(
                    "order"
                ),
            )
        )
        .first()
    )
