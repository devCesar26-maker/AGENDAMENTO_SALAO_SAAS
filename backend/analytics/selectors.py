"""Queries agregadas e tenant-scoped do dashboard, exports e auditoria."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.db.models import (
    Count,
    DurationField,
    ExpressionWrapper,
    F,
    Max,
    Q,
    Sum,
)
from django.db.models.functions import ExtractHour, ExtractWeekDay, TruncMonth
from django.utils import timezone

from analytics.models import AuditLog
from catalog.models import Professional
from scheduling.models import Appointment, AppointmentItem

WEEKDAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
# ExtractWeekDay: 1 = domingo … 7 = sábado.
WEEKDAY_INDEX = {2: 0, 3: 1, 4: 2, 5: 3, 6: 4, 7: 5, 1: 6}  # -> mon..sun

PERIODS = (
    ("morning", "manhã", 0, 12),
    ("afternoon", "tarde", 12, 18),
    ("evening", "noite", 18, 24),
)


def _period_for_hour(hour):
    for key, label, start, end in PERIODS:
        if start <= hour < end:
            return key, label
    return PERIODS[0][0], PERIODS[0][1]


def _occupied_activity(organization, start, end, tz):
    """Minutos ocupados por dia-da-semana e período, em uma única agregação."""
    rows = (
        AppointmentItem.objects.filter(
            organization=organization,
            start_at__gte=start,
            start_at__lt=end,
            appointment__status__in=(
                Appointment.Status.SCHEDULED,
                Appointment.Status.CONFIRMED,
                Appointment.Status.COMPLETED,
                Appointment.Status.NO_SHOW,
            ),
        )
        .annotate(
            weekday=ExtractWeekDay("start_at", tzinfo=tz),
            hour=ExtractHour("start_at", tzinfo=tz),
        )
        .values("weekday", "hour")
        .annotate(
            minutes=Sum(
                ExpressionWrapper(F("end_at") - F("start_at"), output_field=DurationField())
            )
        )
    )
    buckets = {}
    for row in rows:
        weekday = WEEKDAY_INDEX.get(row["weekday"])
        if weekday is None:
            continue
        period_key, _ = _period_for_hour(row["hour"])
        seconds = row["minutes"].total_seconds() if row["minutes"] else 0
        buckets.setdefault((weekday, period_key), 0.0)
        buckets[(weekday, period_key)] += seconds / 60
    return buckets


def _weekly_opening_minutes(organization):
    weekly = []
    for key in WEEKDAY_KEYS:
        total = 0
        for begin, end in (organization.working_hours or {}).get(key, []):
            start = datetime.strptime(begin, "%H:%M")
            finish = datetime.strptime(end, "%H:%M")
            minutes = (finish - start).total_seconds() // 60
            if minutes < 0:
                minutes += 24 * 60
            total += max(0, int(minutes))
        weekly.append(total)
    return weekly


def _weekday_counts(start_date, end_date):
    days = (end_date - start_date).days + 1
    full_weeks, remainder = divmod(days, 7)
    counts = [full_weeks] * 7
    for offset in range(remainder):
        counts[(start_date.weekday() + offset) % 7] += 1
    return counts


def _theoretical_capacity_minutes(organization, start_date, end_date):
    """Minutos configurados por dia-da-semana x ocorrências no período x profissionais."""
    weekly = _weekly_opening_minutes(organization)
    counts = _weekday_counts(start_date, end_date)
    capacity = {}
    for weekday, occurrences in enumerate(counts):
        daily = weekly[weekday]
        for key, _, start, end in PERIODS:
            fraction = max(0, end - start) / 24
            capacity[(weekday, key)] = daily * fraction * occurrences
    return capacity


def _low_occupancy_suggestions(organization, *, threshold, max_items=3):
    tz = ZoneInfo(organization.timezone)
    today = timezone.localdate(timezone=tz)
    start_date = today - timedelta(days=30)
    start = timezone.make_aware(datetime.combine(start_date, datetime.min.time()), tz)
    end = timezone.make_aware(datetime.combine(today, datetime.min.time()), tz)
    activity = _occupied_activity(organization, start, end, tz)
    capacity = _theoretical_capacity_minutes(organization, start_date, today - timedelta(days=1))
    professionals = (
        Professional.objects.filter(organization=organization, is_active=True).count() or 1
    )
    suggestions = []
    for (weekday, period_key), capacity_minutes in capacity.items():
        total_capacity = capacity_minutes * professionals
        if total_capacity <= 0:
            continue
        occupied = activity.get((weekday, period_key), 0.0)
        rate = occupied / total_capacity * 100
        if rate >= threshold:
            continue
        label = next(label for key, label, _, _ in PERIODS if key == period_key)
        suggestions.append(
            {
                "type": "low_occupancy",
                "severity": "warning" if rate < threshold * 0.6 else "info",
                "message": (
                    f"{WEEKDAY_KEYS[weekday]} pela {label} tem baixa ocupação "
                    f"({rate:.0f}% nas últimas 4 semanas)."
                ),
                "reference": {
                    "weekday": WEEKDAY_KEYS[weekday],
                    "period": period_key,
                    "occupancy_rate": round(rate, 2),
                    "occupied_minutes": round(occupied, 2),
                    "capacity_minutes": round(total_capacity, 2),
                },
            }
        )
    suggestions.sort(key=lambda item: item["reference"]["occupancy_rate"])
    return suggestions[:max_items]


def _inactive_customers_suggestion(organization, *, inactive_days, top_n):
    from customers.models import Customer

    cutoff = timezone.now() - timedelta(days=inactive_days)
    rows = (
        Customer.objects.filter(organization=organization, responsavel__isnull=True)
        .annotate(
            last_completed=Max(
                "appointments__items__start_at",
                filter=Q(appointments__status=Appointment.Status.COMPLETED),
            )
        )
        .filter(last_completed__lt=cutoff)
        .order_by("last_completed")[:top_n]
    )
    clients = [
        {
            "id": customer.pk,
            "name": customer.name,
            "last_completed_at": (
                customer.last_completed.isoformat() if customer.last_completed else None
            ),
            "days_since": (
                (timezone.now() - customer.last_completed).days if customer.last_completed else None
            ),
        }
        for customer in rows
    ]
    if not clients:
        return None
    return {
        "type": "inactive_customers",
        "severity": "warning",
        "message": (
            f"{len(clients)} cliente(s) sem retorno há mais de {inactive_days} dias. "
            "Considere uma campanha de reativação."
        ),
        "reference": {"inactive_days": inactive_days, "customers": clients},
    }


def _declining_services_suggestions(organization, *, max_items=3):
    tz = ZoneInfo(organization.timezone)
    today = timezone.localdate(timezone=tz)
    current_start_date = today.replace(day=1)
    previous_start_date = current_start_date
    for _ in range(3):
        previous_start_date = (previous_start_date - timedelta(days=1)).replace(day=1)
    start = timezone.make_aware(datetime.combine(previous_start_date, datetime.min.time()), tz)
    end = timezone.make_aware(datetime.combine(today + timedelta(days=1), datetime.min.time()), tz)
    rows = (
        AppointmentItem.objects.filter(
            organization=organization,
            start_at__gte=start,
            start_at__lt=end,
            appointment__status=Appointment.Status.COMPLETED,
        )
        .annotate(month=TruncMonth("start_at", tzinfo=tz))
        .values("service_id", "service__name", "month")
        .annotate(quantity=Count("pk"))
    )
    by_service = {}
    for row in rows:
        key = (row["service_id"], row["service__name"])
        bucket = by_service.setdefault(key, {"current": 0, "previous": 0})
        month_date = row["month"].astimezone(tz).date() if row["month"] else None
        if month_date is not None and month_date >= current_start_date:
            bucket["current"] += row["quantity"]
        else:
            bucket["previous"] += row["quantity"]
    suggestions = []
    for (service_id, service_name), data in by_service.items():
        previous_total = data["previous"]
        if previous_total < 3:
            continue
        average = previous_total / 3
        if data["current"] >= average * 0.7:
            continue
        suggestions.append(
            {
                "type": "declining_service",
                "severity": "warning" if data["current"] < average * 0.4 else "info",
                "message": (
                    f"O serviço {service_name} caiu para {data['current']} atendimento(s) no mês "
                    f"atual (média anterior de {average:.1f})."
                ),
                "reference": {
                    "service_id": service_id,
                    "service_name": service_name,
                    "current_month": data["current"],
                    "previous_months_average": round(average, 2),
                },
            }
        )
    suggestions.sort(key=lambda item: item["reference"]["current_month"])
    return suggestions[:max_items]


def _professional_imbalance_suggestions(organization, *, max_items=3):
    from catalog.models import WorkingHours

    tz = ZoneInfo(organization.timezone)
    today = timezone.localdate(timezone=tz)
    start_date = today - timedelta(days=30)
    start = timezone.make_aware(datetime.combine(start_date, datetime.min.time()), tz)
    end = timezone.make_aware(datetime.combine(today, datetime.min.time()), tz)
    rows = (
        AppointmentItem.objects.filter(
            organization=organization,
            start_at__gte=start,
            start_at__lt=end,
            appointment__status__in=(
                Appointment.Status.SCHEDULED,
                Appointment.Status.CONFIRMED,
                Appointment.Status.COMPLETED,
                Appointment.Status.NO_SHOW,
            ),
        )
        .values("professional_id", "professional__name")
        .annotate(
            minutes=Sum(
                ExpressionWrapper(F("end_at") - F("start_at"), output_field=DurationField())
            )
        )
    )
    hours_by_professional = {}
    for row in WorkingHours.objects.filter(organization=organization).values(
        "professional_id", "start_time", "end_time"
    ):
        minutes = (
            datetime.combine(datetime.min.date(), row["end_time"])
            - datetime.combine(datetime.min.date(), row["start_time"])
        ).total_seconds() // 60
        if minutes < 0:
            minutes += 24 * 60
        hours_by_professional[row["professional_id"]] = hours_by_professional.get(
            row["professional_id"], 0
        ) + max(0, int(minutes))
    occurrences = _weekday_counts(start_date, today - timedelta(days=1))
    rates = {}
    for row in rows:
        weekly_minutes = hours_by_professional.get(row["professional_id"], 0)
        capacity = (weekly_minutes / 7) * sum(occurrences)
        if capacity <= 0:
            continue
        minutes = row["minutes"].total_seconds() / 60 if row["minutes"] else 0
        rates[row["professional_id"]] = (row["professional__name"], minutes / capacity * 100)
    if not rates:
        return []
    team_average = sum(rate for _, rate in rates.values()) / len(rates)
    suggestions = []
    for professional_id, (name, rate) in rates.items():
        deviation = rate - team_average
        if abs(deviation) < 25:
            continue
        suggestions.append(
            {
                "type": "professional_imbalance",
                "severity": "warning" if abs(deviation) >= 40 else "info",
                "message": (
                    f"{name} está {'acima' if deviation > 0 else 'abaixo'} da média da equipe "
                    f"em ocupação ({rate:.0f}% vs {team_average:.0f}%)."
                ),
                "reference": {
                    "professional_id": professional_id,
                    "professional_name": name,
                    "occupancy_rate": round(rate, 2),
                    "team_average": round(team_average, 2),
                },
            }
        )
    suggestions.sort(key=lambda item: abs(item["reference"]["occupancy_rate"] - team_average))
    return suggestions[:max_items]


def insights(organization, *, inactive_days=60, top_n=5, low_occupancy_threshold=35):
    """Lista determinística de sugestões acionáveis, em poucas queries fixas."""
    suggestions = []
    suggestions.extend(_low_occupancy_suggestions(organization, threshold=low_occupancy_threshold))
    inactive = _inactive_customers_suggestion(
        organization, inactive_days=inactive_days, top_n=top_n
    )
    if inactive is not None:
        suggestions.append(inactive)
    suggestions.extend(_declining_services_suggestions(organization))
    suggestions.extend(_professional_imbalance_suggestions(organization))
    return suggestions


def _items(organization, start, end):
    return AppointmentItem.objects.filter(
        organization=organization, start_at__gte=start, start_at__lt=end
    )


def overview_data(organization, start, end, *, professional_user_id=None):
    appointments = Appointment.objects.filter(
        organization=organization, items__start_at__gte=start, items__start_at__lt=end
    )
    items = _items(organization, start, end)
    professionals = Professional.objects.filter(organization=organization, is_active=True)
    if professional_user_id is not None:
        appointments = appointments.filter(items__professional__user_id=professional_user_id)
        items = items.filter(professional__user_id=professional_user_id)
        professionals = professionals.filter(user_id=professional_user_id)
    totals = appointments.aggregate(
        count=Count("pk", distinct=True),
        canceled=Count("pk", filter=Q(status=Appointment.Status.CANCELED), distinct=True),
        no_show=Count("pk", filter=Q(status=Appointment.Status.NO_SHOW), distinct=True),
    )
    totals["revenue"] = items.filter(appointment__status=Appointment.Status.COMPLETED).aggregate(
        total=Sum("price")
    )["total"]
    totals["occupied"] = items.filter(
        appointment__status__in=(
            Appointment.Status.SCHEDULED,
            Appointment.Status.CONFIRMED,
            Appointment.Status.COMPLETED,
            Appointment.Status.NO_SHOW,
        )
    ).aggregate(
        total=Sum(ExpressionWrapper(F("end_at") - F("start_at"), output_field=DurationField()))
    )[
        "total"
    ]
    totals["professionals"] = professionals.count()
    return totals


def list_services(organization, start, end, *, professional_user_id=None):
    queryset = _items(organization, start, end).filter(
        appointment__status=Appointment.Status.COMPLETED
    )
    if professional_user_id is not None:
        queryset = queryset.filter(professional__user_id=professional_user_id)
    return (
        queryset.values("service_id", service_name=F("service__name"))
        .annotate(quantity=Count("pk"), revenue=Sum("price"))
        .order_by("-quantity", "service__name")
    )


def list_professionals(organization, start, end, *, professional_user_id=None):
    queryset = _items(organization, start, end).filter(
        appointment__status=Appointment.Status.COMPLETED
    )
    if professional_user_id is not None:
        queryset = queryset.filter(professional__user_id=professional_user_id)
    return (
        queryset.values("professional_id", professional_name=F("professional__name"))
        .annotate(appointments=Count("appointment_id", distinct=True), revenue=Sum("price"))
        .order_by("-revenue", "professional_name")
    )


def list_audit_logs(organization, *, action=None, start_at=None, end_at=None):
    queryset = AuditLog.objects.filter(organization=organization).select_related(
        "actor", "actor__user"
    )
    if action:
        queryset = queryset.filter(action=action)
    if start_at:
        queryset = queryset.filter(created_at__gte=start_at)
    if end_at:
        queryset = queryset.filter(created_at__lt=end_at)
    return queryset.order_by("-created_at", "-pk")


def appointment_export_queryset(
    organization, start, end, *, status_value=None, professional_id=None
):
    queryset = (
        Appointment.objects.filter(
            organization=organization, items__start_at__gte=start, items__start_at__lt=end
        )
        .select_related("customer")
        .prefetch_related("items__service", "items__professional")
        .distinct()
        .order_by("pk")
    )
    if status_value:
        queryset = queryset.filter(status=status_value)
    if professional_id:
        queryset = queryset.filter(items__professional_id=professional_id)
    return queryset


def customers_export_queryset(organization):
    from customers.models import Customer

    return Customer.objects.filter(organization=organization).order_by("pk")


def commissions_export_queryset(organization, start, end, *, professional_id=None):
    queryset = (
        _items(organization, start, end)
        .filter(appointment__status=Appointment.Status.COMPLETED)
        .select_related("professional", "service", "appointment")
        .order_by("professional__name", "start_at", "pk")
    )
    if professional_id:
        queryset = queryset.filter(professional_id=professional_id)
    return queryset
