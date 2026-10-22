"""Endpoints anônimos, sempre limitados ao tenant da página de reserva."""

from datetime import timedelta
from typing import ClassVar
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import Throttled
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Professional, ProfessionalService, Service, ServiceCategory
from core.api.throttling import PublicBookingRateThrottle
from core.idempotency import IdempotencyConflict, execute_idempotently
from customers import services as customer_services
from customers.models import Customer
from scheduling import services
from scheduling.models import Appointment, AppointmentToken, Rating
from scheduling.serializers import (
    AvailabilityQuerySerializer,
    AvailabilityResponseSerializer,
    PublicAppointmentCreateSerializer,
    RatingInputSerializer,
)


class PublicCategoryResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    order = serializers.IntegerField()


class PublicServiceResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    category = serializers.IntegerField()
    category_name = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    duration_minutes = serializers.IntegerField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)


class PublicCatalogResponseSerializer(serializers.Serializer):
    categories = PublicCategoryResponseSerializer(many=True)
    services = PublicServiceResponseSerializer(many=True)


class PublicProfessionalResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    photo = serializers.CharField(allow_blank=True, allow_null=True)
    services = serializers.ListField(child=serializers.IntegerField())


PUBLIC_APPOINTMENT_LIMIT_NEW_PER_24H = 3
PUBLIC_APPOINTMENT_LIMIT_RETURNING_PER_24H = 4


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
    @extend_schema(responses=PublicCatalogResponseSerializer)
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
    @extend_schema(responses=PublicProfessionalResponseSerializer(many=True))
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
    @extend_schema(responses=AvailabilityResponseSerializer)
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
                                "discount_percent": item.get("discount_percent", 0),
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
            data=request.data,
            context={"request": request, "organization": organization},
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        now = timezone.now()

        def create_booking():
            # Serializa limite, identidade do cliente e reserva no mesmo tenant.
            with transaction.atomic():
                from billing.services import check_appointment_limit

                check_appointment_limit(organization)
                customer_services.lock_customer_identity(
                    organization, phone=data["phone"], email=data.get("email", "")
                )
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
                    if customer.phone != data["phone"] or (
                        data.get("email")
                        and customer.email
                        and customer.email.casefold() != data["email"].casefold()
                    ):
                        raise serializers.ValidationError(
                            "Os contatos informados não correspondem ao cadastro existente. "
                            "Fale com o salão para atualizar seus dados."
                        )
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
                has_completed_history = Appointment.objects.filter(
                    organization=organization,
                    customer=customer,
                    status=Appointment.Status.COMPLETED,
                ).exists()
                limit = (
                    PUBLIC_APPOINTMENT_LIMIT_RETURNING_PER_24H
                    if has_completed_history
                    else PUBLIC_APPOINTMENT_LIMIT_NEW_PER_24H
                )
                if recent_count >= limit:
                    raise Throttled(
                        detail=(
                            "Limite de reservas atingido para este contato nas últimas 24 horas. "
                            "Tente novamente mais tarde ou fale com o salão."
                        )
                    )

                customer.lgpd_consent = True
                customer.lgpd_consent_at = now
                customer.save(update_fields=["lgpd_consent", "lgpd_consent_at", "updated_at"])
                attendee = data.get("atendido")
                if attendee and attendee["name"].casefold() != customer.name.casefold():
                    dependent = (
                        Customer.objects.filter(
                            organization=organization,
                            responsavel=customer,
                            name__iexact=attendee["name"],
                        )
                        .order_by("pk")
                        .first()
                    )
                    if dependent is None:
                        dependent = Customer.objects.create(
                            organization=organization,
                            responsavel=customer,
                            name=attendee["name"],
                            phone=attendee.get("phone", ""),
                            email=attendee.get("email", "").strip().lower(),
                        )
                    customer = dependent
                appointment = services.create_appointment(
                    organization=organization,
                    customer=customer,
                    items=data["items"],
                    desired_start=data["start_at"],
                    membership=None,
                    origin=Appointment.Origin.PUBLIC_PAGE,
                )

            first_item = appointment.items.order_by("order").first()
            return {
                "id": appointment.pk,
                "status": appointment.status,
                "start_at": (
                    first_item.start_at.isoformat() if first_item else data["start_at"].isoformat()
                ),
                "origin": Appointment.Origin.PUBLIC_PAGE,
            }

        idempotency_key = request.headers.get("Idempotency-Key")
        if idempotency_key:
            if len(idempotency_key) > 255 or not idempotency_key.strip():
                raise serializers.ValidationError({"Idempotency-Key": "Chave inválida."})
            try:
                result, _ = execute_idempotently(
                    organization=organization,
                    context="public_appointment_create",
                    key=idempotency_key,
                    data={
                        "name": data["name"],
                        "phone": data["phone"],
                        "email": data.get("email", ""),
                        "atendido": data.get("atendido", {}),
                        "consent": data["consent"],
                        "start_at": data["start_at"].isoformat(),
                        "items": [
                            {
                                "service": item["service"].pk,
                                "professional": item["professional"].pk,
                                "order": item["order"],
                            }
                            for item in data["items"]
                        ],
                    },
                    operation=create_booking,
                )
            except IdempotencyConflict as error:
                return Response({"detail": str(error)}, status=status.HTTP_409_CONFLICT)
        else:
            result = create_booking()
        return Response(result, status=status.HTTP_201_CREATED)


def _load_appointment_token_or_reject(token_value: str):
    """Retorna (token, resposta_de_erro). Erro só é preenchido quando o token é rejeitado."""
    appointment_token = (
        AppointmentToken.objects.filter(token=token_value)
        .select_related("appointment", "appointment__customer", "appointment__organization")
        .first()
    )
    if appointment_token is None:
        return None, Response({"detail": "Este link é inválido."}, status=status.HTTP_404_NOT_FOUND)
    if appointment_token.used_at is not None:
        return None, Response(
            {"detail": "Este link já foi utilizado."}, status=status.HTTP_410_GONE
        )
    if appointment_token.expires_at <= timezone.now():
        return None, Response(
            {"detail": "Este link expirou. Peça um novo ao salão."}, status=status.HTTP_410_GONE
        )
    return appointment_token, None


def _magic_appointment_payload(appointment_token: AppointmentToken) -> dict:
    """Somente dados que o próprio cliente já conhece; nada é filtrado por request."""
    appointment = appointment_token.appointment
    tz = ZoneInfo(appointment.organization.timezone)
    return {
        "status": appointment.status,
        "organization_name": appointment.organization.name,
        "customer_name": appointment.customer.name,
        "can_cancel": (
            appointment.status in (Appointment.Status.SCHEDULED, Appointment.Status.CONFIRMED)
        ),
        "expires_at": appointment_token.expires_at.isoformat(),
        "items": [
            {
                "service": item.service.name,
                "professional": item.professional.name,
                "start_at": timezone.localtime(item.start_at, tz).isoformat(),
                "end_at": timezone.localtime(item.end_at, tz).isoformat(),
            }
            for item in appointment.items.select_related("service", "professional").order_by(
                "order"
            )
        ],
    }


class PublicAppointmentMagicLinkView(PublicAPIView):
    """GET do link mágico: detalhes de UM agendamento identificado pelo token."""

    @extend_schema(responses={200: dict, 404: dict, 410: dict})
    def get(self, request, token: str):
        appointment_token, rejection = _load_appointment_token_or_reject(token)
        if rejection is not None:
            return rejection
        # O tenant vem do token (dado único de 32 bytes), nunca do request;
        # a resposta só contém dados do agendamento ao qual o token pertence.
        return Response(_magic_appointment_payload(appointment_token))


class PublicAppointmentMagicLinkCancelView(PublicAPIView):
    """POST do link mágico: cancela o agendamento e consome o token (uso único)."""

    @extend_schema(responses={200: dict, 404: dict, 409: dict, 410: dict})
    def post(self, request, token: str):
        appointment_token, rejection = _load_appointment_token_or_reject(token)
        if rejection is not None:
            return rejection
        appointment = appointment_token.appointment
        if appointment.status not in (
            Appointment.Status.SCHEDULED,
            Appointment.Status.CONFIRMED,
        ):
            return Response(
                {"detail": "Este agendamento não pode mais ser cancelado online."},
                status=status.HTTP_409_CONFLICT,
            )
        with transaction.atomic():
            locked = AppointmentToken.objects.select_for_update().get(pk=appointment_token.pk)
            if locked.used_at is not None:
                return Response(
                    {"detail": "Este link já foi utilizado."}, status=status.HTTP_410_GONE
                )
            locked.used_at = timezone.now()
            locked.save(update_fields=["used_at", "updated_at"])
            services.change_appointment_status(appointment, Appointment.Status.CANCELED, actor=None)
        locked.refresh_from_db(fields=["appointment"])
        return Response(_magic_appointment_payload(locked))


def _load_action_token(token_value: str, action: str):
    token, rejection = _load_appointment_token_or_reject(token_value)
    if rejection is not None:
        return None, rejection
    if token.action != action:
        return None, Response({"detail": "Este link é inválido."}, status=status.HTTP_404_NOT_FOUND)
    return token, None


class PublicRatingView(PublicAPIView):
    """GET mostra o atendimento; POST grava uma única avaliação e consome o token."""

    def _payload(self, token):
        appointment = token.appointment
        tz = ZoneInfo(appointment.organization.timezone)
        return {
            "organization_name": appointment.organization.name,
            "customer_name": appointment.customer.name,
            "expires_at": token.expires_at.isoformat(),
            "items": [
                {
                    "service": item.service.name,
                    "professional": item.professional.name,
                    "start_at": timezone.localtime(item.start_at, tz).isoformat(),
                }
                for item in appointment.items.select_related("service", "professional").order_by(
                    "order"
                )
            ],
        }

    @extend_schema(responses={200: dict, 404: dict, 409: dict, 410: dict})
    def get(self, request, token: str):
        appointment_token, rejection = _load_action_token(token, AppointmentToken.Action.RATE)
        if rejection is not None:
            return rejection
        appointment = appointment_token.appointment
        if appointment.status != Appointment.Status.COMPLETED:
            return Response(
                {"detail": "Este atendimento ainda não pode ser avaliado."},
                status=status.HTTP_409_CONFLICT,
            )
        if Rating.objects.filter(appointment=appointment).exists():
            return Response(
                {"detail": "Este atendimento já foi avaliado."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(self._payload(appointment_token))

    @extend_schema(
        request=RatingInputSerializer, responses={201: dict, 404: dict, 409: dict, 410: dict}
    )
    def post(self, request, token: str):
        appointment_token, rejection = _load_action_token(token, AppointmentToken.Action.RATE)
        if rejection is not None:
            return rejection
        serializer = RatingInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            locked = (
                AppointmentToken.objects.select_for_update()
                .select_related("appointment", "appointment__organization")
                .get(pk=appointment_token.pk)
            )
            if locked.used_at is not None or locked.expires_at <= timezone.now():
                return Response(
                    {"detail": "Este link já foi utilizado ou expirou."},
                    status=status.HTTP_410_GONE,
                )
            appointment = locked.appointment
            if appointment.status != Appointment.Status.COMPLETED:
                return Response(
                    {"detail": "Este atendimento ainda não pode ser avaliado."},
                    status=status.HTTP_409_CONFLICT,
                )
            if Rating.objects.filter(appointment=appointment).exists():
                return Response(
                    {"detail": "Este atendimento já foi avaliado."},
                    status=status.HTTP_409_CONFLICT,
                )
            rating = Rating.objects.create(
                organization=appointment.organization,
                appointment=appointment,
                score=serializer.validated_data["score"],
                comment=serializer.validated_data.get("comment", ""),
            )
            locked.used_at = timezone.now()
            locked.save(update_fields=["used_at", "updated_at"])
        return Response(
            {"id": rating.pk, "score": rating.score, "detail": "Avaliação registrada."},
            status=status.HTTP_201_CREATED,
        )


class PublicRecurringSuggestionView(PublicAPIView):
    """Confirmação ou recusa explícita de uma sugestão de recorrência."""

    def _load(self, token):
        appointment_token, rejection = _load_action_token(token, AppointmentToken.Action.CONFIRM)
        if rejection is not None:
            return None, rejection
        appointment = appointment_token.appointment
        if appointment.status != Appointment.Status.SUGGESTED:
            return None, Response(
                {"detail": "Esta sugestão não está mais disponível."},
                status=status.HTTP_409_CONFLICT,
            )
        if (
            appointment.suggestion_expires_at is None
            or appointment.suggestion_expires_at <= timezone.now()
        ):
            return None, Response({"detail": "Esta sugestão expirou."}, status=status.HTTP_410_GONE)
        return appointment_token, None

    def _payload(self, token):
        appointment = token.appointment
        tz = ZoneInfo(appointment.organization.timezone)
        return {
            "organization_name": appointment.organization.name,
            "customer_name": appointment.customer.name,
            "status": appointment.status,
            "expires_at": appointment.suggestion_expires_at.isoformat(),
            "items": [
                {
                    "service": item.service.name,
                    "professional": item.professional.name,
                    "start_at": timezone.localtime(item.start_at, tz).isoformat(),
                    "end_at": timezone.localtime(item.end_at, tz).isoformat(),
                }
                for item in appointment.items.select_related("service", "professional").order_by(
                    "order"
                )
            ],
        }

    @extend_schema(responses={200: dict, 404: dict, 409: dict, 410: dict})
    def get(self, request, token: str):
        appointment_token, rejection = self._load(token)
        if rejection is not None:
            return rejection
        return Response(self._payload(appointment_token))

    @extend_schema(responses={200: dict, 404: dict, 409: dict, 410: dict})
    def post(self, request, token: str, decision: str):
        if decision not in {"confirm", "decline"}:
            return Response({"detail": "Decisão inválida."}, status=status.HTTP_400_BAD_REQUEST)
        appointment_token, rejection = self._load(token)
        if rejection is not None:
            return rejection
        payload = self._payload(appointment_token)
        with transaction.atomic():
            locked = AppointmentToken.objects.select_for_update().get(pk=appointment_token.pk)
            if locked.used_at is not None:
                return Response(
                    {"detail": "Este link já foi utilizado."}, status=status.HTTP_410_GONE
                )
            appointment = Appointment.objects.select_for_update().get(pk=locked.appointment_id)
            if appointment.status != Appointment.Status.SUGGESTED:
                return Response(
                    {"detail": "Esta sugestão não está mais disponível."},
                    status=status.HTTP_409_CONFLICT,
                )
            if decision == "confirm":
                appointment = services.change_appointment_status(
                    appointment, Appointment.Status.CONFIRMED
                )
                from notifications.models import NotificationEvent
                from notifications.services import queue_appointment_notification

                queue_appointment_notification(appointment, NotificationEvent.Kind.CONFIRMATION)
                services.ensure_magic_link_token(appointment)
            else:
                appointment.status = Appointment.Status.CANCELED
                appointment.suggestion_expires_at = None
                appointment.save(update_fields=["status", "suggestion_expires_at", "updated_at"])
                from notifications.services import start_waitlist_priority_for_appointment

                start_waitlist_priority_for_appointment(appointment)
            locked.used_at = timezone.now()
            locked.save(update_fields=["used_at", "updated_at"])
        payload["status"] = appointment.status
        if decision == "confirm":
            payload["expires_at"] = None
        return Response(payload)
