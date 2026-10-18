"""
Endpoints de clientes (views finas; regras em services/selectors). Todos
escopados ao tenant via `TenantModelViewSet` (core/tenant).
"""

from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from core.api.pagination import DefaultPagination
from core.tenant import (
    MembershipRequired,
    TenantModelViewSet,
    TenantSerializerContextMixin,
    resolve_tenant,
)

from . import selectors, services
from .models import Customer
from .serializers import CustomerSerializer, LgpdConsentSerializer


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
