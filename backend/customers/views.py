"""
Endpoints de clientes (views finas; regras em services/selectors). Todos
escopados ao tenant via `TenantModelViewSet` (core/tenant).
"""

from drf_spectacular.utils import extend_schema
from django.db import transaction
from rest_framework import generics, serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.serializers import ModelSerializer

from analytics.models import AuditLog
from analytics.services import record_audit
from core.api.pagination import DefaultPagination
from core.tenant import (
    MembershipRequired,
    TenantModelViewSet,
    TenantSerializerContextMixin,
    resolve_tenant,
)

from organizations.permissions import IsTenantManagerOrOwner
from organizations.selectors import get_active_membership
from scheduling.models import Appointment, AppointmentItem

from . import selectors, services
from .models import Customer
from .serializers import CustomerSerializer, LgpdConsentSerializer


class CustomerExportAppointmentItemSerializer(ModelSerializer):
    service_name = serializers.CharField(source="service.name", read_only=True)
    professional_name = serializers.CharField(source="professional.name", read_only=True)

    class Meta:
        model = AppointmentItem
        fields = (
            "id", "service", "service_name", "professional", "professional_name", "order",
            "start_at", "end_at", "buffer_minutes", "price", "commission_percentage",
        )


class CustomerExportAppointmentSerializer(ModelSerializer):
    items = CustomerExportAppointmentItemSerializer(many=True, read_only=True)

    class Meta:
        model = Appointment
        fields = (
            "id", "status", "origin", "created_by", "notes", "reminder_sent_at",
            "created_at", "updated_at", "items",
        )


class CustomerExportSerializer(ModelSerializer):
    appointments = CustomerExportAppointmentSerializer(many=True, read_only=True)

    class Meta:
        model = Customer
        fields = (
            "id", "name", "phone", "email", "responsavel", "notes", "birthday",
            "lgpd_consent", "lgpd_consent_at", "created_at", "updated_at", "appointments",
        )


class _CustomerManagerView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated, IsTenantManagerOrOwner]
    queryset = Customer.objects.none()

    def get_queryset(self):
        organization = self.request.organization or resolve_tenant(self.request)
        return Customer.objects.filter(organization=organization).prefetch_related(
            "appointments__items__service", "appointments__items__professional"
        )


class CustomerExportView(_CustomerManagerView):
    def get(self, request, *args, **kwargs):
        customer = self.get_object()
        return Response(CustomerExportSerializer(customer).data)


class CustomerAnonymizeView(_CustomerManagerView):
    def post(self, request, *args, **kwargs):
        customer = self.get_object()
        organization = customer.organization
        membership = get_active_membership(request.user, organization)
        with transaction.atomic():
            customer.name = "Cliente removido"
            customer.phone = ""
            customer.email = ""
            customer.notes = ""
            customer.responsavel = None
            customer.birthday = None
            customer.lgpd_consent = False
            customer.lgpd_consent_at = None
            customer.save(
                update_fields=(
                    "name", "phone", "email", "notes", "responsavel", "birthday",
                    "lgpd_consent", "lgpd_consent_at", "updated_at",
                )
            )
            customer.appointments.update(notes="")
            record_audit(
                organization=organization,
                action=AuditLog.Action.CUSTOMER_ANONYMIZED,
                actor=membership,
                object_type="Customer",
                object_id=customer.pk,
                context={"customer_id": customer.pk},
            )
        return Response({"detail": "Dados pessoais do cliente anonimizados."}, status=status.HTTP_200_OK)


@extend_schema(tags=["customers"])
class CustomerListCreateView(
    TenantModelViewSet, TenantSerializerContextMixin, generics.ListCreateAPIView
):
    """
    CRUD de clientes: qualquer membro do salão pode criar/editar (decisão de
    design: profissionais anotam dados de seus clientes no atendimento).
    Busca `?search=` por nome/telefone/e-mail + paginação.
    """

    serializer_class = CustomerSerializer
    pagination_class = DefaultPagination
    permission_classes = [MembershipRequired]
    queryset = Customer.objects.none()  # Stub para o gerador de schema.

    def get_queryset(self):
        organization = self.request.organization or resolve_tenant(self.request)
        return selectors.list_customers(
            organization, search=self.request.query_params.get("search")
        )


@extend_schema(tags=["customers"])
class CustomerDetailView(
    TenantModelViewSet,
    TenantSerializerContextMixin,
    generics.RetrieveUpdateDestroyAPIView,
):
    """DETALHE/PATCH/DELETE de cliente (member-level; escopado ao tenant)."""

    serializer_class = CustomerSerializer
    pagination_class = DefaultPagination
    permission_classes = [MembershipRequired]
    queryset = Customer.objects.none()  # Stub para o gerador de schema.

    def get_queryset(self):
        organization = self.request.organization or resolve_tenant(self.request)
        return Customer.objects.filter(organization=organization)


@extend_schema(tags=["customers"])
class CustomerLgpdConsentView(generics.GenericAPIView):
    """
    POST `/customers/{id}/lgpd-consent/`: registra ou revoga o consentimento
    LGPD do cliente, carimbando `lgpd_consent_at` no servidor.
    """

    queryset = Customer.objects.none()  # Stub para o gerador de schema.
    serializer_class = LgpdConsentSerializer
    permission_classes = [MembershipRequired]

    def get_queryset(self):
        organization = self.request.organization or resolve_tenant(self.request)
        return Customer.objects.filter(organization=organization)

    def post(self, request, *args, **kwargs):
        customer = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = services.register_lgpd_consent(
            customer, consented=serializer.validated_data["consented"]
        )
        return Response(
            CustomerSerializer(customer, context=self.get_serializer_context()).data,
            status=status.HTTP_200_OK,
        )
