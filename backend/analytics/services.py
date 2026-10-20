"""Cálculos de domínio e escrita de auditoria para analytics."""

from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from analytics import selectors
from analytics.models import AuditLog

SAFE_AUDIT_CONTEXT_KEYS = {
    "from_tier",
    "to_tier",
    "status",
    "commission_percentage",
    "customer_id",
}


def record_audit(*, organization, action, actor=None, object_type, object_id="", context=None):
    """Persiste contexto allowlisted; callers never pass request payloads."""
    safe_context = {
        key: str(value) for key, value in (context or {}).items() if key in SAFE_AUDIT_CONTEXT_KEYS
    }
    if actor is not None and actor.organization_id != organization.pk:
        actor = None
    return AuditLog.objects.create(
        organization=organization,
        actor=actor,
        action=action,
        object_type=object_type,
        object_id=str(object_id)[:64],
        context=safe_context,
    )


def period_for(organization, data):
    tz = ZoneInfo(organization.timezone)
    today = timezone.now().astimezone(tz).date()
    start_date = data.get("data_inicio") or today.replace(day=1)
    end_date = data.get("data_fim") or (today.replace(day=28) + timedelta(days=4)).replace(
        day=1
    ) - timedelta(days=1)
    if end_date < start_date:
        raise ValidationError({"data_fim": "A data final deve ser igual ou posterior à inicial."})
    start = timezone.make_aware(datetime.combine(start_date, time.min), tz)
    end = timezone.make_aware(datetime.combine(end_date + timedelta(days=1), time.min), tz)
    return start, end, start_date, end_date


def _opening_minutes(organization, start_date, end_date):
    """Configured weekly opening minutes times the number of matching weekdays."""
    keys = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    weekly = [
        sum(
            max(
                0,
                int(
                    (
                        datetime.combine(datetime.min.date(), time.fromisoformat(end))
                        - datetime.combine(datetime.min.date(), time.fromisoformat(begin))
                    ).total_seconds()
                    // 60
                ),
            )
            for begin, end in (organization.working_hours or {}).get(key, [])
        )
        for key in keys
    ]
    days = (end_date - start_date).days + 1
    full_weeks, remainder = divmod(days, 7)
    counts = [full_weeks] * 7
    for offset in range(remainder):
        counts[(start_date.weekday() + offset) % 7] += 1
    return sum(weekly[weekday] * count for weekday, count in enumerate(counts))


def overview(organization, start, end, start_date, end_date, *, professional_user_id=None):
    data = selectors.overview_data(
        organization, start, end, professional_user_id=professional_user_id
    )
    count = data["count"] or 0
    canceled = data["canceled"] or 0
    no_show = data["no_show"] or 0
    occupied = data["occupied"] or timedelta(0)
    capacity = _opening_minutes(organization, start_date, end_date) * data["professionals"]
    occupied_minutes = Decimal(str(occupied.total_seconds())) / Decimal(60)
    active_count = count - canceled
    return {
        "total_appointments": count,
        "occupancy_rate": (round(float(occupied_minutes / capacity * 100), 2) if capacity else 0.0),
        "no_show_rate": round(no_show / active_count * 100, 2) if active_count else 0.0,
        "estimated_revenue": data["revenue"] or Decimal("0.00"),
    }
