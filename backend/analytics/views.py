"""Endpoints de métricas, exportação e auditoria."""

import csv
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.http import StreamingHttpResponse
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from analytics import selectors, services
from analytics.models import AuditLog
from analytics.serializers import (
    AppointmentExportQuerySerializer,
    AuditLogSerializer,
    InsightSerializer,
    InsightsQuerySerializer,
    OverviewSerializer,
    PeriodQuerySerializer,
    ProfessionalMetricSerializer,
    ServiceMetricSerializer,
)
from core.api.pagination import DefaultPagination
from core.tenant import resolve_membership
from organizations.models import Membership
from organizations.permissions import IsTenantManagerOrOwner


class MetricsAccess(IsAuthenticated):
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        _, membership = resolve_membership(request)
        return membership is not None


class CsvEcho:
    def write(self, value):
        return value


def _safe_csv(value):
    value = "" if value is None else str(value)
    if value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def _csv_response(rows, filename):
    writer = csv.writer(CsvEcho())

    def stream():
        yield "\ufeff"
        for row in rows:
            yield writer.writerow([_safe_csv(value) for value in row])

    response = StreamingHttpResponse(stream(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


class _MetricsBase(APIView):
    permission_classes = [MetricsAccess]
    query_serializer_class = PeriodQuerySerializer

    def get_data(self, request):
        serializer = self.query_serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        organization, membership = resolve_membership(request)
        start, end, start_date, end_date = services.period_for(
            organization, serializer.validated_data
        )
        professional_id = (
            request.user.pk if membership.role == Membership.Role.PROFESSIONAL else None
        )
        return organization, start, end, start_date, end_date, professional_id


@extend_schema(tags=["analytics"], responses=OverviewSerializer)
class MetricsOverviewView(_MetricsBase):
    def get(self, request):
        organization, start, end, start_date, end_date, professional_id = self.get_data(request)
        result = services.overview(
            organization,
            start,
            end,
            start_date,
            end_date,
            professional_user_id=professional_id,
        )
        return Response(OverviewSerializer(result).data)


@extend_schema(tags=["analytics"], responses=ServiceMetricSerializer(many=True))
class MetricsServicesView(_MetricsBase):
    def get(self, request):
        organization, start, end, _, _, professional_id = self.get_data(request)
        rows = selectors.list_services(
            organization, start, end, professional_user_id=professional_id
        )
        return Response(ServiceMetricSerializer(rows, many=True).data)


@extend_schema(tags=["analytics"], responses=ProfessionalMetricSerializer(many=True))
class MetricsProfessionalsView(_MetricsBase):
    def get(self, request):
        organization, start, end, _, _, professional_id = self.get_data(request)
        rows = selectors.list_professionals(
            organization, start, end, professional_user_id=professional_id
        )
        return Response(ProfessionalMetricSerializer(rows, many=True).data)


@extend_schema(tags=["analytics"], responses=InsightSerializer(many=True))
class InsightsView(APIView):
    """Sugestões acionáveis; agregações ficam em poucas queries fixas no selector."""

    permission_classes = [IsTenantManagerOrOwner]

    def get(self, request):
        query = InsightsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        organization, _ = resolve_membership(request)
        rows = selectors.insights(
            organization,
            inactive_days=query.validated_data["inactive_days"],
            top_n=query.validated_data["top_n"],
            low_occupancy_threshold=query.validated_data["low_occupancy_threshold"],
        )
        paginator = DefaultPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        return paginator.get_paginated_response(InsightSerializer(page, many=True).data)


class _ExportBase(APIView):
    permission_classes = [IsTenantManagerOrOwner]

    def period(self, request, *, include_filters=False):
        serializer_class = (
            AppointmentExportQuerySerializer if include_filters else PeriodQuerySerializer
        )
        query = serializer_class(data=request.query_params)
        query.is_valid(raise_exception=True)
        organization, _ = resolve_membership(request)
        start, end, start_date, end_date = services.period_for(organization, query.validated_data)
        return organization, start, end, start_date, end_date, query.validated_data


@extend_schema(tags=["exports"])
class AppointmentsExportView(_ExportBase):
    def get(self, request):
        organization, start, end, _, _, filters = self.period(request, include_filters=True)
        professional_id = filters.get("profissional")
        if (
            professional_id
            and not organization.catalog_professional_set.filter(
                pk=professional_id, organization=organization
            ).exists()
        ):
            raise ValidationError(
                {"profissional": "Profissional não encontrado nesta organização."}
            )
        queryset = selectors.appointment_export_queryset(
            organization,
            start,
            end,
            status_value=filters.get("status"),
            professional_id=professional_id,
        )

        def rows():
            yield [
                "agendamento_id",
                "cliente",
                "telefone",
                "status",
                "servicos",
                "profissionais",
                "inicio",
                "fim",
            ]
            for appointment in queryset.iterator(chunk_size=500):
                items = list(appointment.items.all())
                yield [
                    appointment.pk,
                    appointment.customer.name,
                    appointment.customer.phone,
                    appointment.status,
                    "; ".join(item.service.name for item in items),
                    "; ".join(dict.fromkeys(item.professional.name for item in items)),
                    min((item.start_at for item in items), default=""),
                    max((item.end_at for item in items), default=""),
                ]

        return _csv_response(rows(), "agendamentos.csv")


@extend_schema(tags=["exports"])
class CustomersExportView(_ExportBase):
    def get(self, request):
        organization, _, _, _, _, _ = self.period(request)
        queryset = selectors.customers_export_queryset(organization)

        def rows():
            yield ["cliente_id", "nome", "telefone", "email", "aniversario"]
            for customer in queryset.iterator(chunk_size=500):
                yield [
                    customer.pk,
                    customer.name,
                    customer.phone,
                    customer.email,
                    customer.birthday,
                ]

        return _csv_response(rows(), "clientes.csv")


@extend_schema(tags=["exports"])
class CommissionsExportView(_ExportBase):
    def get(self, request):
        organization, start, end, _, _, filters = self.period(request, include_filters=True)
        professional_id = filters.get("profissional")
        queryset = selectors.commissions_export_queryset(
            organization, start, end, professional_id=professional_id
        )

        def rows():
            yield [
                "agendamento_id",
                "profissional",
                "servico",
                "preco",
                "comissao_percentual",
                "comissao",
            ]
            for item in queryset.iterator(chunk_size=500):
                commission = item.price * item.commission_percentage / Decimal("100")
                yield [
                    item.appointment_id,
                    item.professional.name,
                    item.service.name,
                    item.price,
                    item.commission_percentage,
                    commission.quantize(Decimal("0.01")),
                ]

        return _csv_response(rows(), "comissoes.csv")


class AuditLogListView(generics.ListAPIView):
    serializer_class = AuditLogSerializer
    permission_classes = [IsTenantManagerOrOwner]
    pagination_class = DefaultPagination
    queryset = AuditLog.objects.none()

    def get_queryset(self):
        organization, _ = resolve_membership(self.request)
        query = PeriodQuerySerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)
        action = self.request.query_params.get("action") or self.request.query_params.get("acao")
        if action and action not in AuditLog.Action.values:
            raise ValidationError({"acao": "Tipo de ação inválido."})
        tz = ZoneInfo(organization.timezone)
        start_date = query.validated_data.get("data_inicio")
        end_date = query.validated_data.get("data_fim")
        start_at = (
            timezone.make_aware(datetime.combine(start_date, time.min), tz) if start_date else None
        )
        end_at = (
            timezone.make_aware(datetime.combine(end_date + timedelta(days=1), time.min), tz)
            if end_date
            else None
        )
        return selectors.list_audit_logs(
            organization,
            action=action,
            start_at=start_at,
            end_at=end_at,
        )
