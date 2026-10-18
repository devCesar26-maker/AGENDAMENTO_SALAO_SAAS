"""Regras de negócio e motor de disponibilidade de agendamentos."""

from datetime import UTC, datetime, time, timedelta
from datetime import date as Date
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from catalog.models import Professional, ProfessionalService
from core.sanitization import sanitize_free_text
from scheduling.models import Appointment, AppointmentItem
from scheduling.selectors import load_availability_data

SLOT_STEP_MINUTES = 15
WEEKDAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class SlotUnavailable(APIException):
    status_code = 409
    default_detail = "Este horário não está mais disponível. Escolha outro horário."
    default_code = "slot_unavailable"


def _valid_localizations(naive: datetime, tz: ZoneInfo) -> list[datetime]:
    """Resolve horário local ignorando horas inexistentes e mantendo ambas as folds."""
    values = []
    for fold in (0, 1):
        aware = naive.replace(tzinfo=tz, fold=fold)
        roundtrip = aware.astimezone(UTC).astimezone(tz).replace(tzinfo=None)
        if roundtrip == naive and all(item.utcoffset() != aware.utcoffset() for item in values):
            values.append(aware)
    return values


def _local_intervals(hours_by_day, day: Date, tz: ZoneInfo, *, intervals):
    if intervals:
        values = hours_by_day.get(WEEKDAY_KEYS[day.weekday()], [])
    else:
        values = [
            [row.start_time.strftime("%H:%M"), row.end_time.strftime("%H:%M")]
            for row in hours_by_day.get(day.weekday(), [])
        ]
    result = []
    for start_value, end_value in values:
        start_time = (
            time.fromisoformat(start_value) if isinstance(start_value, str) else start_value
        )
        end_time = time.fromisoformat(end_value) if isinstance(end_value, str) else end_value
        start_naive = datetime.combine(day, start_time)
        end_day = day + timedelta(days=1) if end_time <= start_time else day
        end_naive = datetime.combine(end_day, end_time)
        starts = _valid_localizations(start_naive, tz)
        ends = _valid_localizations(end_naive, tz)
        if starts and ends:
            result.append((starts[0].astimezone(UTC), ends[-1].astimezone(UTC)))
    return result


def _organization_intervals(organization, day, tz):
    return _local_intervals(organization.working_hours or {}, day, tz, intervals=True)


def _professional_intervals(hours, professional_id, start_day, end_day, tz):
    by_day = {}
    for row in hours:
        if row.professional_id == professional_id:
            by_day.setdefault(row.weekday, []).append(row)
    result = []
    day = start_day
    while day <= end_day:
        result.extend(_local_intervals(by_day, day, tz, intervals=False))
        day += timedelta(days=1)
    return result


def _overlaps(start, end, other_start, other_end):
    return start < other_end and other_start < end


def calcular_slots_disponiveis(
    organization,
    services,
    professionals,
    date,
    *,
    slot_step_minutes=SLOT_STEP_MINUTES,
    exclude_appointment_id=None,
):
    """Retorna inícios disponíveis e a atribuição de profissionais para cada item.

    ``services`` e ``professionals`` devem estar na mesma ordem; cada profissional
    pode ser objeto/ID ou ``None``/``"any"`` para seleção automática. Os serviços
    são encadeados na ordem recebida e o buffer do item fica entre esse item e o
    seguinte. Apenas slots começando em incrementos de 15 minutos são oferecidos.
    """
    if not services or len(services) != len(professionals):
        return []
    if isinstance(date, str):
        date = Date.fromisoformat(date)
    services = list(services)
    if any(service.organization_id != organization.id for service in services):
        return []

    tz = ZoneInfo(organization.timezone)
    organization_intervals = _organization_intervals(organization, date, tz)
    if not organization_intervals:
        return []
    window_start = min(start for start, _ in organization_intervals)
    window_end = max(end for _, end in organization_intervals)
    links, hours, time_offs, busy_items = load_availability_data(
        organization,
        services,
        date,
        window_start,
        window_end,
        exclude_appointment_id=exclude_appointment_id,
    )
    links_by_service = {}
    for link in links:
        links_by_service.setdefault(link.service_id, []).append(link)

    options = []
    for service, requested_professional in zip(services, professionals, strict=True):
        requested_id = getattr(requested_professional, "pk", requested_professional)
        if requested_id in (None, "any"):
            service_links = links_by_service.get(service.pk, [])
        else:
            service_links = [
                link
                for link in links_by_service.get(service.pk, [])
                if link.professional_id == requested_id
            ]
        options.append(service_links)
    if any(not service_links for service_links in options):
        return []

    work_cache = {}

    def professional_works(professional_id, start, occupied_until):
        local_start = start.astimezone(tz).date()
        local_end = occupied_until.astimezone(tz).date()
        key = (professional_id, local_start, local_end)
        if key not in work_cache:
            work_cache[key] = _professional_intervals(
                hours, professional_id, local_start, local_end, tz
            )
        return any(
            work_start <= start and occupied_until <= work_end
            for work_start, work_end in work_cache[key]
        )

    def is_free(professional_id, start, occupied_until):
        for off in time_offs:
            if off.professional_id != professional_id:
                continue
            local_day = start.astimezone(tz).date()
            last_day = (occupied_until - timedelta(microseconds=1)).astimezone(tz).date()
            if off.start_date <= last_day and off.end_date >= local_day:
                return False
        for existing in busy_items:
            if existing.professional_id != professional_id:
                continue
            existing_start = existing.start_at
            existing_end = existing.end_at + timedelta(minutes=existing.buffer_minutes)
            if _overlaps(start, occupied_until, existing_start, existing_end):
                return False
        return True

    def assign_sequence(index, cursor, opening_end, proposed):
        if index == len(services):
            return proposed
        service = services[index]
        for link in options[index]:
            duration = link.duration_override or service.duration_minutes
            service_end = cursor + timedelta(minutes=duration)
            between_buffer = service.buffer_minutes if index < len(services) - 1 else 0
            occupied_until = service_end + timedelta(minutes=between_buffer)
            if (
                service_end > opening_end
                or occupied_until > opening_end
                or not professional_works(link.professional_id, cursor, occupied_until)
                or not is_free(link.professional_id, cursor, occupied_until)
            ):
                continue
            snapshot = {
                "service": service,
                "professional": link.professional,
                "start_at": cursor,
                "end_at": service_end,
                "buffer_minutes": service.buffer_minutes,
                "price": (
                    link.price_override if link.price_override is not None else service.price
                ),
                "commission_percentage": link.commission_percentage,
            }
            result = assign_sequence(index + 1, occupied_until, opening_end, [*proposed, snapshot])
            if result is not None:
                return result
        return None

    slots = {}
    for opening_start, opening_end in organization_intervals:
        candidate = opening_start
        while candidate < opening_end:
            proposed = assign_sequence(0, candidate, opening_end, [])
            if proposed is not None and candidate.astimezone(tz).date() == date:
                slots.setdefault(candidate, proposed)
            candidate += timedelta(minutes=slot_step_minutes)
    return [
        {"start_at": start, "items": items}
        for start, items in sorted(slots.items(), key=lambda pair: pair[0])
    ]


def _validate_booking_data(organization, customer, items, membership):
    if customer.organization_id != organization.id:
        raise ValidationError({"customer": "Cliente não pertence a esta organização."})
    if not items:
        raise ValidationError({"items": "Informe ao menos um serviço."})
    if membership is not None and membership.organization_id != organization.id:
        raise ValidationError("Membership não pertence a esta organização.")
    pairs = set()
    for item in items:
        if (
            item["service"].organization_id != organization.id
            or item["professional"].organization_id != organization.id
        ):
            raise ValidationError("Serviço ou profissional não pertence a esta organização.")
        if not item["service"].is_active or not item["professional"].is_active:
            raise ValidationError("Serviço e profissional precisam estar ativos.")
        pairs.add((item["service"].pk, item["professional"].pk))
    linked_pairs = set(
        ProfessionalService.objects.filter(
            organization=organization,
            service_id__in={service_id for service_id, _ in pairs},
            professional_id__in={professional_id for _, professional_id in pairs},
        ).values_list("service_id", "professional_id")
    )
    if not pairs.issubset(linked_pairs):
        raise ValidationError(
            "Cada profissional precisa estar vinculado ao serviço correspondente."
        )


@transaction.atomic
def create_appointment(
    *, organization, customer, items, desired_start, membership, notes="", origin=None
):
    """Bloqueia profissionais, revalida o slot e cria snapshots atomicamente."""
    from billing.services import check_appointment_limit

    check_appointment_limit(organization)
    _validate_booking_data(organization, customer, items, membership)
    if timezone.is_naive(desired_start):
        raise ValidationError({"start_at": "Informe um horário com fuso horário."})
    desired_start = desired_start.astimezone(UTC)
    ordered_items = sorted(items, key=lambda value: value["order"])
    professional_ids = sorted({item["professional"].pk for item in ordered_items})
    locked_professionals = list(
        Professional.objects.select_for_update()
        .filter(organization=organization, pk__in=professional_ids)
        .order_by("pk")
    )
    if len(locked_professionals) != len(professional_ids):
        raise ValidationError("Profissional não pertence a esta organização.")

    # Bloqueia também as linhas existentes no intervalo; o lock da linha do
    # profissional acima serializa requisições quando ainda não há item no slot.
    end_hint = desired_start + timedelta(days=2)
    list(
        AppointmentItem.objects.select_for_update()
        .filter(
            organization=organization,
            professional_id__in=professional_ids,
            start_at__lt=end_hint,
            end_at__gte=desired_start - timedelta(days=1),
            appointment__status__in=[
                Appointment.Status.SCHEDULED,
                Appointment.Status.CONFIRMED,
            ],
        )
        .select_related("service", "appointment")
    )

    services = [item["service"] for item in ordered_items]
    professionals = [item["professional"] for item in ordered_items]
    local_date = desired_start.astimezone(ZoneInfo(organization.timezone)).date()
    slots = calcular_slots_disponiveis(organization, services, professionals, local_date)
    selected = next((slot for slot in slots if slot["start_at"] == desired_start), None)
    if selected is None:
        raise SlotUnavailable()

    appointment = Appointment.objects.create(
        organization=organization,
        customer=customer,
        created_by=membership,
        notes=sanitize_free_text(notes),
        origin=origin or Appointment.Origin.DASHBOARD,
    )
    for order, snapshot in enumerate(selected["items"]):
        AppointmentItem.objects.create(
            organization=organization,
            appointment=appointment,
            service=snapshot["service"],
            professional=snapshot["professional"],
            order=order,
            start_at=snapshot["start_at"],
            end_at=snapshot["end_at"],
            buffer_minutes=snapshot["buffer_minutes"],
            price=snapshot["price"],
            commission_percentage=snapshot["commission_percentage"],
        )
    from notifications.models import NotificationEvent
    from notifications.services import (
        mark_waitlist_entries_converted,
        queue_appointment_notification,
    )

    mark_waitlist_entries_converted(appointment)
    queue_appointment_notification(appointment, NotificationEvent.Kind.CONFIRMATION)
    return appointment


@transaction.atomic
def reschedule_appointment(*, organization, appointment, desired_start):
    """Trava o agendamento/profissionais e reaplica a disponibilidade no novo início."""
    if timezone.is_naive(desired_start):
        raise ValidationError({"start_at": "Informe um horário com fuso horário."})
    desired_start = desired_start.astimezone(UTC)
    current_appointment = Appointment.objects.get(organization=organization, pk=appointment.pk)
    current_professional_ids = list(
        current_appointment.items.order_by("professional_id")
        .values_list("professional_id", flat=True)
        .distinct()
    )
    list(
        Professional.objects.select_for_update()
        .filter(organization=organization, pk__in=current_professional_ids)
        .order_by("pk")
    )
    locked_appointment = Appointment.objects.select_for_update().get(
        organization=organization, pk=appointment.pk
    )
    if locked_appointment.status not in {
        Appointment.Status.SCHEDULED,
        Appointment.Status.CONFIRMED,
    }:
        raise ValidationError("Somente agendamentos ativos podem ser remarcados.")
    items = list(
        locked_appointment.items.select_for_update()
        .select_related("service", "professional")
        .order_by("order")
    )
    if not items:
        raise ValidationError("Agendamento sem serviços não pode ser remarcado.")
    professional_ids = sorted({item.professional_id for item in items})
    end_hint = desired_start + timedelta(days=2)
    list(
        AppointmentItem.objects.select_for_update()
        .filter(
            organization=organization,
            professional_id__in=professional_ids,
            start_at__lt=end_hint,
            end_at__gte=desired_start - timedelta(days=1),
            appointment__status__in=[
                Appointment.Status.SCHEDULED,
                Appointment.Status.CONFIRMED,
            ],
        )
        .exclude(appointment_id=locked_appointment.pk)
        .order_by("pk")
    )
    proposed = calcular_slots_disponiveis(
        organization,
        [item.service for item in items],
        [item.professional for item in items],
        desired_start.astimezone(ZoneInfo(organization.timezone)).date(),
        exclude_appointment_id=locked_appointment.pk,
    )
    selected = next((slot for slot in proposed if slot["start_at"] == desired_start), None)
    if selected is None:
        raise SlotUnavailable()
    for existing, snapshot in zip(items, selected["items"], strict=True):
        existing.start_at = snapshot["start_at"]
        existing.end_at = snapshot["end_at"]
        existing.buffer_minutes = snapshot["buffer_minutes"]
        existing.price = snapshot["price"]
        existing.commission_percentage = snapshot["commission_percentage"]
        existing.save(
            update_fields=[
                "start_at",
                "end_at",
                "buffer_minutes",
                "price",
                "commission_percentage",
            ]
        )
    return locked_appointment


@transaction.atomic
def change_appointment_status(appointment, status_value):
    allowed = {value for value, _ in Appointment.Status.choices}
    if status_value not in allowed:
        raise ValidationError({"status": "Status de agendamento inválido."})
    previous_status = appointment.status
    appointment.status = status_value
    appointment.save(update_fields=["status", "updated_at"])
    if status_value == Appointment.Status.CANCELED and previous_status != status_value:
        from notifications.models import NotificationEvent
        from notifications.services import queue_appointment_notification

        queue_appointment_notification(appointment, NotificationEvent.Kind.CANCELLATION)
        queue_appointment_notification(appointment, NotificationEvent.Kind.WAITLIST_OPENING)
    return appointment
