"""Endpoints autenticados e públicos da lista de espera."""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from core.api.pagination import DefaultPagination
from core.api.throttling import PublicBookingRateThrottle
from core.tenant import TenantSerializerContextMixin, resolve_membership
from customers import services as customer_services
from customers.models import Customer
from notifications.models import WaitlistEntry
from notifications.permissions import WaitlistManagerAccess
from notifications.selectors import list_waitlist_entries
from notifications.serializers import PublicWaitlistEntrySerializer, WaitlistEntrySerializer


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
            data=request.data, context={"request": request, "organization": organization}
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
            data=request.data, context={"request": request, "organization": organization}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            customer_services.lock_customer_identity(
                organization, phone=data["phone"], email=data["email"]
            )
            identity = Q(phone=data["phone"]) | Q(email__iexact=data["email"])
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
                if (
                    customer.phone != data["phone"]
                    or customer.email.casefold() != data["email"].casefold()
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
                "detail": "Você entrou na lista de espera. Avisaremos por e-mail se surgir um horário.",
            },
            status=status.HTTP_201_CREATED,
        )
