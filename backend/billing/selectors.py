"""Consultas de billing sempre escopadas explicitamente à organização."""

from django.utils import timezone

from billing.models import Plan, Subscription


def list_plans():
    return Plan.objects.all()


def get_subscription(organization):
    return Subscription.objects.select_related("plan").filter(organization=organization).first()


def get_monthly_usage(organization, *, now=None):
    from catalog.models import Professional
    from scheduling.models import Appointment

    now = timezone.localtime(now or timezone.now())
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )
    return {
        "professionals": Professional.objects.filter(organization=organization).count(),
        "appointments": Appointment.objects.filter(
            organization=organization, created_at__gte=start, created_at__lt=end
        )
        .exclude(status=Appointment.Status.CANCELED)
        .count(),
        "period_start": start,
        "period_end": end,
    }
