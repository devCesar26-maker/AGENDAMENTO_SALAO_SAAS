"""API versionada de disponibilidade e agendamentos."""

from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Professional, Service
from core.api.pagination import DefaultPagination
from core.tenant import MembershipRequired, TenantSerializerContextMixin, resolve_membership
from organizations.models import Membership
from scheduling import selectors, services
from scheduling.models import Appointment
from scheduling.permissions import AppointmentAccess, AppointmentCreateAccess
from scheduling.serializers import (
    AppointmentCreateSerializer,
    AppointmentRescheduleSerializer,
    AppointmentSerializer,
    AppointmentStatusSerializer,
    AvailabilityQuerySerializer,
    AvailabilityResponseSerializer,
)


@extend_schema(tags=["scheduling"])
class AvailabilityView(APIView):
    permission_classes = [MembershipRequired]

    @extend_schema(responses=AvailabilityResponseSerializer)
    def get(self, request):
        query = AvailabilityQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        organization = request.organization
        service_ids = query.validated_data["services"]
        services_qs = Service.objects.filter(organization=organization, pk__in=service_ids)
        service_map = {service.pk: service for service in services_qs.select_related("category")}
        if len(service_map) != len(service_ids):
            return Response(
                {"detail": "Um ou mais serviços não pertencem a esta organização."}, status=404
            )
        service_list = [service_map[pk] for pk in service_ids]
        professional_id = query.validated_data["professional"]
        if (
            professional_id is not None
            and not Professional.objects.filter(
                organization=organization, pk=professional_id, is_active=True
            ).exists()
        ):
            return Response(
                {"detail": "Profissional não encontrado nesta organização."}, status=404
            )
        professionals = [professional_id] * len(service_list)
        slots = services.calcular_slots_disponiveis(
            organization, service_list, professionals, query.validated_data["date"]
        )
        return Response(
            {
                "date": query.validated_data["date"],
                "timezone": organization.timezone,
                "slots": [
                    {
                        "start_at": slot["start_at"],
                        "items": [
                            {
                                "service": item["service"].pk,
                                "professional": item["professional"].pk,
                                "start_at": item["start_at"],
                                "end_at": item["end_at"],
                                "price": item["price"],
                                "commission_percentage": item["commission_percentage"],
                            }
                            for item in slot["items"]
                        ],
                    }
                    for slot in slots
                ],
            }
        )


@extend_schema(tags=["scheduling"])
class AppointmentListCreateView(TenantSerializerContextMixin, generics.ListCreateAPIView):
    serializer_class = AppointmentSerializer
    pagination_class = DefaultPagination
    permission_classes = [MembershipRequired]
    queryset = Appointment.objects.none()

    def get_permissions(self):
        if self.request.method == "POST":
            return [AppointmentCreateAccess()]
        return [AppointmentAccess()]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return AppointmentCreateSerializer
        return AppointmentSerializer

    def get_queryset(self):
        organization, membership = resolve_membership(self.request)
        params = self.request.query_params
        date = params.get("date")
        if date:
            from datetime import date as Date

            try:
                date = Date.fromisoformat(date)
            except ValueError as exc:
                raise ValidationError({"date": "Informe a data no formato YYYY-MM-DD."}) from exc
        professional = params.get("professional")
        customer = params.get("customer")
        for field, value in (("professional", professional), ("customer", customer)):
            if value and not value.isdecimal():
                raise ValidationError({field: "Informe um ID numérico válido."})
        status_value = params.get("status")
        if status_value and status_value not in Appointment.Status.values:
            raise ValidationError({"status": "Status de agendamento inválido."})
        queryset = selectors.list_appointments(
            organization,
            date=date,
            professional=professional,
            status=status_value,
            customer=customer,
        )
        if membership.role == Membership.Role.PROFESSIONAL:
            queryset = queryset.filter(items__professional__user=self.request.user).distinct()
        return queryset

    def create(self, request, *args, **kwargs):
        organization, membership = resolve_membership(request)
        serializer = AppointmentCreateSerializer(
            data=request.data,
            context={"request": request, "organization": organization},
        )
        serializer.is_valid(raise_exception=True)
        items = serializer.validated_data["items"]
        if membership.role == Membership.Role.PROFESSIONAL and any(
            item["professional"].user_id != request.user.pk for item in items
        ):
            return Response(
                {"detail": "Profissionais só podem agendar serviços no próprio perfil."},
                status=status.HTTP_403_FORBIDDEN,
            )
        appointment = services.create_appointment(
            organization=organization,
            customer=serializer.validated_data["customer"],
            items=items,
            desired_start=serializer.validated_data["start_at"],
            membership=membership,
            notes=serializer.validated_data.get("notes", ""),
        )
        appointment = selectors.get_appointment(organization, appointment.pk)
        return Response(AppointmentSerializer(appointment).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["scheduling"])
class AppointmentDetailView(generics.RetrieveAPIView):
    serializer_class = AppointmentSerializer
    permission_classes = [AppointmentAccess]
    queryset = Appointment.objects.none()

    def get_queryset(self):
        organization, membership = resolve_membership(self.request)
        queryset = (
            Appointment.objects.filter(organization=organization)
            .select_related("customer", "created_by__user")
            .prefetch_related("items__service", "items__professional")
        )
        if membership.role == Membership.Role.PROFESSIONAL:
            queryset = queryset.filter(items__professional__user=self.request.user).distinct()
        return queryset


@extend_schema(tags=["scheduling"])
class AppointmentStatusView(generics.GenericAPIView):
    serializer_class = AppointmentStatusSerializer
    permission_classes = [AppointmentAccess]
    queryset = Appointment.objects.none()

    def get_queryset(self):
        organization, membership = resolve_membership(self.request)
        queryset = Appointment.objects.filter(organization=organization).prefetch_related("items")
        if membership.role == Membership.Role.PROFESSIONAL:
            queryset = queryset.filter(items__professional__user=self.request.user).distinct()
        return queryset

    def patch(self, request, *args, **kwargs):
        appointment = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        appointment = services.change_appointment_status(
            appointment, serializer.validated_data["status"]
        )
        return Response(
            AppointmentSerializer(
                selectors.get_appointment(request.organization, appointment.pk)
            ).data
        )


@extend_schema(tags=["scheduling"])
class AppointmentRescheduleView(generics.GenericAPIView):
    serializer_class = AppointmentRescheduleSerializer
    permission_classes = [AppointmentAccess]
    queryset = Appointment.objects.none()

    def get_queryset(self):
        organization, membership = resolve_membership(self.request)
        queryset = Appointment.objects.filter(organization=organization)
        if membership.role == Membership.Role.PROFESSIONAL:
            queryset = queryset.filter(items__professional__user=self.request.user).distinct()
        return queryset

    def patch(self, request, *args, **kwargs):
        appointment = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        appointment = services.reschedule_appointment(
            organization=request.organization,
            appointment=appointment,
            desired_start=serializer.validated_data["start_at"],
        )
        return Response(
            AppointmentSerializer(
                selectors.get_appointment(request.organization, appointment.pk)
            ).data
        )


@extend_schema(tags=["scheduling"])
class AppointmentCancelView(AppointmentStatusView):
    """Cancelamento explícito por POST; não há DELETE destrutivo."""

    def post(self, request, *args, **kwargs):
        appointment = self.get_object()
        appointment = services.change_appointment_status(appointment, Appointment.Status.CANCELED)
        return Response(
            AppointmentSerializer(
                selectors.get_appointment(request.organization, appointment.pk)
            ).data
        )
