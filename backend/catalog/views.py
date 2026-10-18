"""
Endpoints de catálogo (views finas; regras de negócio em services/selectors).

Todos escopados ao tenant via `TenantModelViewSet` (core/tenant): o queryset é
filtrado pela membership ativa e o `organization` das gravações vem do
servidor. Sem membership → nenhuma linha visível (fail-closed).
"""

from django.db.models.deletion import ProtectedError
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import SAFE_METHODS
from rest_framework.response import Response

from catalog import selectors, services
from catalog.models import (
    Professional,
    ProfessionalService,
    Service,
    ServiceCategory,
    TimeOff,
    WorkingHours,
)
from catalog.permissions import NestedProfessionalAccess, ProfessionalObjectPermission
from catalog.serializers import (
    ProfessionalLinkUpdateSerializer,
    ProfessionalLinkWriteSerializer,
    ProfessionalSerializer,
    ProfessionalWriteSerializer,
    ServiceCategorySerializer,
    ServiceLinkReadSerializer,
    ServiceSerializer,
    TimeOffSerializer,
    WorkingHoursSerializer,
)
from core.api.exceptions import BusinessError
from core.api.pagination import DefaultPagination
from core.tenant import (
    MembershipRequired,
    TenantModelViewSet,
    TenantSerializerContextMixin,
    resolve_membership,
    resolve_tenant,
)
from organizations.permissions import IsTenantManagerOrOwner


def _write_permissions() -> list:
    """Permissões de escrita da própria membership resolvida no request."""
    return [MembershipRequired(), IsTenantManagerOrOwner()]


class _NestedProfessionalMixin:
    """Resolve o `Professional` da URL escopado ao tenant (404 caso contrário)."""

    def get_professional(self) -> Professional:
        organization = getattr(self.request, "organization", None) or resolve_tenant(
            self.request
        )
        professional = selectors.get_professional(
            organization, self.kwargs["professional_id"]
        )
        if professional is None:
            from django.http import Http404

            raise Http404("Profissional não encontrado neste salão.")
        return professional


class _TenantViewSetBase(TenantModelViewSet, TenantSerializerContextMixin):
    """Comportamento comum: stub de queryset para schema + paginação + fail-closed."""

    pagination_class = DefaultPagination
    queryset = None  # Cada view define o stub para o gerador de schema.

    def get_permissions(self):
        """Default: leitura para qualquer membro; escrita restrita por view."""
        if self.request.method in ("POST", "PATCH", "PUT", "DELETE"):
            return _write_permissions()
        return [MembershipRequired()]


@extend_schema(tags=["catalog"])
class ServiceCategoryListCreateView(_TenantViewSetBase, generics.ListCreateAPIView):
    """Lista (membro) e criação (OWNER+MANAGER) de categorias de serviço."""

    serializer_class = ServiceCategorySerializer
    queryset = ServiceCategory.objects.all()
    filterset_fields = ["is_active"]

    def get_queryset(self):
        organization = self.request.organization or resolve_tenant(self.request)
        return selectors.list_service_categories(organization)


class ServiceCategoryDetailView(
    _TenantViewSetBase, generics.RetrieveUpdateDestroyAPIView
):
    """DETALHE/PATCH/DELETE de categoria — OWNER+MANAGER escrevem."""

    serializer_class = ServiceCategorySerializer
    queryset = ServiceCategory.objects.all()

    def get_queryset(self):
        organization = self.request.organization or resolve_tenant(self.request)
        return ServiceCategory.objects.filter(organization=organization)

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError as exc:
            raise BusinessError(
                "Categoria em uso por um ou mais serviços; desvincule antes de excluir.",
                code="category_in_use",
            ) from exc


@extend_schema(tags=["catalog"])
class ServiceListCreateView(_TenantViewSetBase, generics.ListCreateAPIView):
    """Lista de serviços (membro; filtros `category`, `is_active`); criação MANAGER+."""

    serializer_class = ServiceSerializer
    queryset = Service.objects.all()
    filterset_fields = ["category", "is_active"]

    def get_queryset(self):
        organization = self.request.organization or resolve_tenant(self.request)
        return selectors.list_services(organization)


class ServiceDetailView(_TenantViewSetBase, generics.RetrieveUpdateDestroyAPIView):
    """DETALHE/PATCH/DELETE de serviço — OWNER+MANAGER escrevem."""

    serializer_class = ServiceSerializer
    queryset = Service.objects.all()

    def get_queryset(self):
        organization = self.request.organization or resolve_tenant(self.request)
        return selectors.list_services(organization)


@extend_schema(tags=["catalog"])
class ProfessionalListCreateView(_TenantViewSetBase, generics.ListCreateAPIView):
    """Profissionais do salão (com serviços vinculados); criação OWNER+MANAGER."""

    filterset_fields = ["is_active"]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ProfessionalWriteSerializer
        return ProfessionalSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Professional.objects.none()
        organization = self.request.organization or resolve_tenant(self.request)
        return selectors.list_professionals(organization)

    def create(self, request, *args, **kwargs):
        """Responde com o serializer de LEITURA (objetos, não PKs)."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        professional = serializer.save(organization=request.organization)
        output = ProfessionalSerializer(
            professional, context={**self.get_serializer_context(), "request": request}
        )
        return Response(output.data, status=status.HTTP_201_CREATED)


class ProfessionalDetailView(_TenantViewSetBase, generics.RetrieveUpdateDestroyAPIView):
    """
    DETALHE (membro) / PATCH / DELETE:
    - PATCH: OWNER+MANAGER em qualquer um; PROFESSIONAL só nos próprios dados
      básicos (name, photo) — `user` e `is_active` viram leitura para ele;
    - DELETE: apenas OWNER+MANAGER.
    """

    queryset = Professional.objects.all()

    def get_serializer_class(self):
        if self.request.method in ("PATCH", "PUT"):
            return ProfessionalWriteSerializer
        return ProfessionalSerializer

    def get_permissions(self):
        if self.request.method == "DELETE":
            return _write_permissions()
        if self.request.method in SAFE_METHODS:
            return [MembershipRequired()]
        return [MembershipRequired(), ProfessionalObjectPermission()]

    def get_queryset(self):
        organization = self.request.organization or resolve_tenant(self.request)
        return Professional.objects.filter(organization=organization)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        _, membership = resolve_membership(self.request)
        if membership is not None:
            context["role"] = membership.role
        return context


@extend_schema(tags=["catalog"])
class ProfessionalServiceListCreateView(
    _NestedProfessionalMixin, _TenantViewSetBase, generics.ListCreateAPIView
):
    """
    Serviços vinculados a um profissional:
    - GET: vínculos existentes (membro);
    - POST: OWNER+MANAGER em qualquer profissional; PROFESSIONAL no próprio,
      com preço/duração/comissão customizados.
    """

    queryset = ProfessionalService.objects.all()

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ProfessionalLinkWriteSerializer
        return ServiceLinkReadSerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [MembershipRequired(), NestedProfessionalAccess()]
        return [MembershipRequired()]

    def get_queryset(self):
        return selectors.list_professional_services(self.get_professional())

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        link = services.link_service_to_professional(
            professional=self.get_professional(),
            service=serializer.validated_data["service"],
            price_override=serializer.validated_data.get("price_override"),
            duration_override=serializer.validated_data.get("duration_override"),
            commission_percentage=serializer.validated_data.get(
                "commission_percentage"
            ),
        )
        return Response(
            ServiceLinkReadSerializer(link, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )


class ProfessionalServiceDetailView(
    _TenantViewSetBase, generics.RetrieveUpdateDestroyAPIView
):
    """
    PATCH/DELETE de um vínculo (ajuste de overrides/comissão ou desvinculação).
    OWNER+MANAGER em qualquer um; PROFESSIONAL só nos próprios registros (403).
    """

    queryset = ProfessionalService.objects.all()

    def get_serializer_class(self):
        if self.request.method in ("PATCH", "PUT"):
            return ProfessionalLinkUpdateSerializer
        return ServiceLinkReadSerializer

    def get_permissions(self):
        if self.request.method in ("PATCH", "PUT", "DELETE"):
            return [MembershipRequired(), ProfessionalObjectPermission()]
        return [MembershipRequired()]

    def get_queryset(self):
        organization = self.request.organization or resolve_tenant(self.request)
        return ProfessionalService.objects.filter(
            organization=organization
        ).select_related("service", "service__category", "professional")

    def destroy(self, request, *args, **kwargs):
        services.unlink_service_to_professional(self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["catalog"])
class WorkingHoursListCreateView(
    _NestedProfessionalMixin, _TenantViewSetBase, generics.ListCreateAPIView
):
    """
    Horário de trabalho semanal:
    - GET: janelas do profissional (membro);
    - POST: OWNER+MANAGER em qualquer um; PROFESSIONAL no próprio (403 caso
      contrário).
    """

    serializer_class = WorkingHoursSerializer
    queryset = WorkingHours.objects.all()

    def get_permissions(self):
        if self.request.method == "POST":
            return [MembershipRequired(), NestedProfessionalAccess()]
        return [MembershipRequired()]

    def get_queryset(self):
        return selectors.list_working_hours(self.get_professional())

    def perform_create(self, serializer):
        organization, _ = resolve_membership(self.request)
        serializer.save(organization=organization, professional=self.get_professional())


class WorkingHoursDetailView(_TenantViewSetBase, generics.RetrieveUpdateDestroyAPIView):
    """DETALHE/PATCH/DELETE de uma janela semanal (regra do profissional do vínculo)."""

    serializer_class = WorkingHoursSerializer
    queryset = WorkingHours.objects.all()

    def get_permissions(self):
        if self.request.method in ("PATCH", "PUT", "DELETE"):
            return [MembershipRequired(), ProfessionalObjectPermission()]
        return [MembershipRequired()]

    def get_queryset(self):
        organization = self.request.organization or resolve_tenant(self.request)
        return WorkingHours.objects.filter(organization=organization)


@extend_schema(tags=["catalog"])
class TimeOffListCreateView(
    _NestedProfessionalMixin, _TenantViewSetBase, generics.ListCreateAPIView
):
    """
    Folgas/bloqueios do profissional:
    - GET (membro); POST: OWNER+MANAGER qualquer um; PROFESSIONAL no próprio.
    """

    serializer_class = TimeOffSerializer
    queryset = TimeOff.objects.all()

    def get_permissions(self):
        if self.request.method == "POST":
            return [MembershipRequired(), NestedProfessionalAccess()]
        return [MembershipRequired()]

    def get_queryset(self):
        return selectors.list_time_offs(self.get_professional())

    def perform_create(self, serializer):
        organization, _ = resolve_membership(self.request)
        serializer.save(organization=organization, professional=self.get_professional())


class TimeOffDetailView(_TenantViewSetBase, generics.RetrieveUpdateDestroyAPIView):
    """DETALHE/PATCH/DELETE de uma folga (regra do profissional do vínculo)."""

    serializer_class = TimeOffSerializer
    queryset = TimeOff.objects.all()

    def get_permissions(self):
        if self.request.method in ("PATCH", "PUT", "DELETE"):
            return [MembershipRequired(), ProfessionalObjectPermission()]
        return [MembershipRequired()]

    def get_queryset(self):
        organization = self.request.organization or resolve_tenant(self.request)
        return TimeOff.objects.filter(organization=organization)
