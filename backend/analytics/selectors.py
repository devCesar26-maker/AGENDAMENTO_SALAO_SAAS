"""Queries agregadas e tenant-scoped do dashboard, exports e auditoria."""

from django.db.models import Count, DurationField, ExpressionWrapper, F, Q, Sum

from analytics.models import AuditLog
from catalog.models import Professional
from scheduling.models import Appointment, AppointmentItem


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
