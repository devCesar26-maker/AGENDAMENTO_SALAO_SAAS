"""Endpoints anônimos, sempre limitados ao tenant da página de reserva."""

from datetime import timedelta
from typing import ClassVar

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import Throttled
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Professional, ProfessionalService, Service, ServiceCategory
from core.api.throttling import PublicBookingRateThrottle
from customers.models import Customer
from organizations.models import Organization
from scheduling import services
from scheduling.models import Appointment
from scheduling.serializers import (
    AvailabilityQuerySerializer,
    PublicAppointmentCreateSerializer,
)

PUBLIC_APPOINTMENT_LIMIT_PER_24H = 3


class PublicAPIView(APIView):
    authentication_classes: ClassVar[list] = []
    permission_classes: ClassVar[list] = [AllowAny]
    throttle_classes: ClassVar[list] = [PublicBookingRateThrottle]

    @property
    def organization(self):
        organization = getattr(self.request, "organization", None)
        if organization is None:
            raise serializers.ValidationError("Organização pública não identificada.")
        return organization


class PublicCatalogView(PublicAPIView):
    def get(self, request):
        organization = self.organization
        services_qs = Service.objects.filter(
            organization=organization,
            is_active=True,
            category__is_active=True,
        ).select_related("category")
        categories = ServiceCategory.objects.filter(
            organization=organization,
            is_active=True,
            services__in=services_qs,
        ).distinct()
        return Response(
            {
                "categories": [
                    {"id": category.pk, "name": category.name, "order": category.order}
                    for category in categories
                ],
                "services": [
                    {
                        "id": service.pk,
                        "category": service.category_id,
                        "category_name": service.category.name,
                        "name": service.name,
                        "description": service.description,
                        "duration_minutes": service.duration_minutes,
                        "price": service.price,
                    }
                    for service in services_qs
                ],
            }
        )


class PublicProfessionalsView(PublicAPIView):
    def get(self, request):
        organization = self.organization
        links = ProfessionalService.objects.filter(
            organization=organization,
            professional__is_active=True,
            service__is_active=True,
            service__category__is_active=True,
        ).select_related("professional")
        services_by_professional = {}
        professionals = {}
        for link in links:
            professionals[link.professional_id] = link.professional
            services_by_professional.setdefault(link.professional_id, []).append(link.service_id)
        return Response(
            [
                {
                    "id": professional.pk,
                    "name": professional.name,
                    "photo": professional.photo,
                    "services": sorted(services_by_professional[professional.pk]),
                }
                for professional in professionals.values()
            ]
        )


class PublicAvailabilityView(PublicAPIView):
    def get(self, request):
        query = AvailabilityQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        organization = self.organization
        service_ids = query.validated_data["services"]
        service_map = {
            service.pk: service
            for service in Service.objects.filter(
                organization=organization,
                pk__in=service_ids,
                is_active=True,
                category__is_active=True,
            ).select_related("category")
        }
        if len(service_map) != len(service_ids):
            return Response(
                {"detail": "Um ou mais serviços não pertencem a esta organização."},
                status=status.HTTP_404_NOT_FOUND,
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
                {"detail": "Profissional não encontrado nesta organização."},
                status=status.HTTP_404_NOT_FOUND,
            )
        slots = services.calcular_slots_disponiveis(
            organization,
            service_list,
            [professional_id] * len(service_list),
            query.validated_data["date"],
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
                            }
                            for item in slot["items"]
                        ],
                    }
                    for slot in slots
                ],
            }
        )


class PublicAppointmentCreateView(PublicAPIView):
    serializer_class = PublicAppointmentCreateSerializer

    def post(self, request):
        organization = self.organization
        serializer = self.serializer_class(
            data=request.data, context={"request": request, "organization": organization}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        now = timezone.now()

        # Serializa a verificação do limite e a criação/reuso de cliente no tenant.
        with transaction.atomic():
            organization = Organization.objects.select_for_update().get(pk=organization.pk)
            identity = Q(phone=data["phone"])
            if data.get("email"):
                identity |= Q(email__iexact=data["email"])
            matches = list(
                Customer.objects.select_for_update()
                .filter(organization=organization)
                .filter(identity)
                .order_by("pk")[:2]
            )
            if len(matches) > 1:
                raise serializers.ValidationError(
                    "Telefone e e-mail estão associados a clientes diferentes. Contate o salão."
                )
            if matches:
                customer = matches[0]
            else:
                customer, _ = Customer.objects.get_or_create(
                    organization=organization,
                    phone=data["phone"],
                    defaults={"name": data["name"], "email": data.get("email", "")},
                )

            recent_count = Appointment.objects.filter(
                organization=organization,
                customer=customer,
                created_at__gte=now - timedelta(hours=24),
            ).count()
            if recent_count >= PUBLIC_APPOINTMENT_LIMIT_PER_24H:
                raise Throttled(
                    detail=(
                        "Limite de reservas atingido para este contato nas últimas 24 horas. "
                        "Tente novamente mais tarde ou fale com o salão."
                    )
                )

            customer.name = data["name"]
            customer.phone = data["phone"]
            customer.email = data.get("email", "")
            customer.lgpd_consent = True
            customer.lgpd_consent_at = now
            customer.save(
                update_fields=[
                    "name",
                    "phone",
                    "email",
                    "lgpd_consent",
                    "lgpd_consent_at",
                    "updated_at",
                ]
            )
            appointment = services.create_appointment(
                organization=organization,
                customer=customer,
                items=data["items"],
                desired_start=data["start_at"],
                membership=None,
                origin=Appointment.Origin.PUBLIC_PAGE,
            )

        first_item = appointment.items.order_by("order").first()
        return Response(
            {
                "id": appointment.pk,
                "status": appointment.status,
                "start_at": first_item.start_at if first_item else data["start_at"],
                "origin": Appointment.Origin.PUBLIC_PAGE,
            },
            status=status.HTTP_201_CREATED,
        )
