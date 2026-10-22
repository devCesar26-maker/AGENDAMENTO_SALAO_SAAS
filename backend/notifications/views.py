"""Endpoints autenticados e públicos da lista de espera."""

from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers, status
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from core.api.pagination import DefaultPagination
from core.api.throttling import PublicBookingRateThrottle
from core.idempotency import IdempotencyConflict, execute_idempotently
from core.tenant import TenantSerializerContextMixin, resolve_membership
from customers import services as customer_services
from customers.models import Customer
from notifications.models import WaitlistEntry, WaitlistOffer
from notifications.permissions import WaitlistManagerAccess
from notifications.selectors import list_waitlist_entries, waitlist_offer_for_token
from notifications.serializers import (
    PublicWaitlistEntrySerializer,
    PublicWaitlistOfferBookSerializer,
    WaitlistEntrySerializer,
)
from scheduling import services as scheduling_services
from scheduling.models import Appointment


@extend_schema(tags=["waitlist"])
class WaitlistEntryListCreateView(TenantSerializerContextMixin, generics.ListCreateAPIView):
    serializer_class = WaitlistEntrySerializer
    permission_classes = [WaitlistManagerAccess]
    pagination_class = DefaultPagination

    def get_queryset(self):
        organization, _ = resolve_membership(self.request)
        return list_waitlist_entries(organization)

    def create(self, request, *args, **kwargs):
        organization, _ = resolve_membership(request)
        serializer = self.get_serializer(
            data=request.data,
            context={"request": request, "organization": organization},
        )
        serializer.is_valid(raise_exception=True)
        entry = serializer.save(organization=organization)
        return Response(
            self.get_serializer(
                entry, context={"request": request, "organization": organization}
            ).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["waitlist"])
class WaitlistEntryDeleteView(generics.DestroyAPIView):
    serializer_class = WaitlistEntrySerializer
    permission_classes = [WaitlistManagerAccess]
    queryset = WaitlistEntry.objects.none()

    def get_queryset(self):
        organization, _ = resolve_membership(self.request)
        return WaitlistEntry.objects.filter(organization=organization).select_related(
            "customer", "service", "professional"
        )


@extend_schema(tags=["public-booking"])
class PublicWaitlistEntryCreateView(generics.CreateAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [PublicBookingRateThrottle]
    serializer_class = PublicWaitlistEntrySerializer

    def create(self, request, *args, **kwargs):
        organization = getattr(request, "organization", None)
        if organization is None:
            raise serializers.ValidationError("Organização pública não identificada.")
        serializer = self.get_serializer(
            data=request.data,
            context={"request": request, "organization": organization},
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            customer_services.lock_customer_identity(
                organization, phone=data["phone"], email=data["email"]
            )
            identity = Q(phone=data["phone"])
            if data["email"]:
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
            now = timezone.now()
            if matches:
                customer = matches[0]
                if customer.phone != data["phone"] or (
                    data["email"] and customer.email.casefold() != data["email"].casefold()
                ):
                    raise serializers.ValidationError(
                        "Os contatos informados não correspondem ao cadastro existente. "
                        "Fale com o salão para atualizar seus dados."
                    )
                customer.lgpd_consent = True
                customer.lgpd_consent_at = now
                customer.save(
                    update_fields=[
                        "lgpd_consent",
                        "lgpd_consent_at",
                    ]
                )
            else:
                customer = Customer.objects.create(
                    organization=organization,
                    name=data["name"],
                    phone=data["phone"],
                    email=data["email"],
                    lgpd_consent=True,
                    lgpd_consent_at=now,
                )
            entry = WaitlistEntry.objects.create(
                organization=organization,
                customer=customer,
                service=data["service"],
                professional=data.get("professional"),
                desired_date=data["desired_date"],
            )

        return Response(
            {
                "id": entry.pk,
                "desired_date": entry.desired_date,
                "detail": "Sua inscrição na lista de espera foi registrada.",
            },
            status=status.HTTP_201_CREATED,
        )


class PriorityOfferUnavailable(APIException):
    status_code = status.HTTP_410_GONE
    default_detail = "Esta oferta prioritária expirou ou já foi utilizada."
    default_code = "priority_offer_unavailable"


class PublicWaitlistOfferView(generics.GenericAPIView):
    """Link exclusivo do primeiro da fila; reserva somente o item ofertado."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [PublicBookingRateThrottle]
    serializer_class = PublicWaitlistOfferBookSerializer

    def _load(self, token):
        offer = waitlist_offer_for_token(token)
        if offer is None:
            return None, Response(
                {"detail": "Este link é inválido."}, status=status.HTTP_404_NOT_FOUND
            )
        if not offer.is_active:
            return None, Response(
                {"detail": "Esta oferta expirou ou já foi utilizada."},
                status=status.HTTP_410_GONE,
            )
        return offer, None

    def _payload(self, offer):
        tz = ZoneInfo(offer.organization.timezone)
        item = offer.appointment_item
        return {
            "organization_name": offer.organization.name,
            "customer_name": offer.entry.customer.name,
            "service": item.service.name,
            "professional": item.professional.name,
            "start_at": timezone.localtime(item.start_at, tz).isoformat(),
            "end_at": timezone.localtime(item.end_at, tz).isoformat(),
            "price": item.price,
            "expires_at": offer.expires_at.isoformat(),
        }

    @extend_schema(responses={200: dict, 404: dict, 410: dict})
    def get(self, request, token):
        offer, rejection = self._load(token)
        if rejection is not None:
            return rejection
        return Response(self._payload(offer))

    @extend_schema(
        request=PublicWaitlistOfferBookSerializer,
        responses={201: dict, 404: dict, 410: dict},
    )
    def post(self, request, token):
        offer, rejection = self._load(token)
        if rejection is not None:
            return rejection
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        def book():
            with transaction.atomic():
                locked = (
                    WaitlistOffer.objects.select_for_update()
                    .select_related(
                        "organization",
                        "entry",
                        "entry__customer",
                        "appointment_item",
                        "appointment_item__service",
                        "appointment_item__professional",
                    )
                    .filter(pk=offer.pk)
                    .first()
                )
                if locked is None or not locked.is_active:
                    raise PriorityOfferUnavailable()
                customer = locked.entry.customer
                now = timezone.now()
                customer.lgpd_consent = True
                customer.lgpd_consent_at = now
                customer.save(update_fields=["lgpd_consent", "lgpd_consent_at", "updated_at"])
                item = locked.appointment_item
                appointment = scheduling_services.create_appointment(
                    organization=locked.organization,
                    customer=customer,
                    items=[
                        {
                            "service": item.service,
                            "professional": item.professional,
                            "order": 0,
                        }
                    ],
                    desired_start=item.start_at,
                    membership=None,
                    origin=Appointment.Origin.PUBLIC_PAGE,
                    waitlist_offer=locked,
                )
                first = appointment.items.order_by("order").first()
                return {
                    "id": appointment.pk,
                    "status": appointment.status,
                    "start_at": first.start_at.isoformat() if first else None,
                }

        idempotency_key = request.headers.get("Idempotency-Key")
        try:
            if idempotency_key:
                if len(idempotency_key) > 255 or not idempotency_key.strip():
                    raise serializers.ValidationError({"Idempotency-Key": "Chave inválida."})
                result, _ = execute_idempotently(
                    organization=offer.organization,
                    context="public_waitlist_offer_book",
                    key=idempotency_key,
                    data={"offer": offer.pk, "consent": True},
                    operation=book,
                )
            else:
                result = book()
        except IdempotencyConflict as error:
            return Response({"detail": str(error)}, status=status.HTTP_409_CONFLICT)
        return Response(result, status=status.HTTP_201_CREATED)
