"""Serializers explícitos para entradas administrativas e públicas da espera."""

import re
from zoneinfo import ZoneInfo

from django.utils import timezone
from rest_framework import serializers

from catalog.models import Professional, ProfessionalService, Service
from core.sanitization import sanitize_free_text
from customers.models import Customer
from notifications.models import WaitlistEntry


class WaitlistEntrySerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    service_name = serializers.CharField(source="service.name", read_only=True)
    professional_name = serializers.CharField(
        source="professional.name", read_only=True, allow_null=True
    )

    class Meta:
        model = WaitlistEntry
        fields = (
            "id",
            "customer",
            "customer_name",
            "service",
            "service_name",
            "professional",
            "professional_name",
            "desired_date",
            "created_at",
            "notified_at",
            "converted_at",
        )
        read_only_fields = ("id", "created_at", "notified_at", "converted_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        organization = self.context.get("organization")
        if organization:
            self.fields["customer"].queryset = Customer.objects.filter(organization=organization)
            self.fields["service"].queryset = Service.objects.filter(organization=organization)
            self.fields["professional"].queryset = Professional.objects.filter(
                organization=organization
            )

    def validate(self, attrs):
        organization = self.context["organization"]
        service = attrs["service"]
        professional = attrs.get("professional")
        if not service.is_active:
            raise serializers.ValidationError({"service": "O serviço precisa estar ativo."})
        if professional:
            if not professional.is_active:
                raise serializers.ValidationError(
                    {"professional": "O profissional precisa estar ativo."}
                )
            if not ProfessionalService.objects.filter(
                organization=organization, service=service, professional=professional
            ).exists():
                raise serializers.ValidationError(
                    {"professional": "Profissional não oferece este serviço."}
                )
        return attrs


class PublicWaitlistEntrySerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120, trim_whitespace=True)
    phone = serializers.CharField(max_length=20, trim_whitespace=True)
    email = serializers.EmailField(max_length=254, required=False, allow_blank=True, default="")
    consent = serializers.BooleanField()
    service = serializers.PrimaryKeyRelatedField(queryset=Service.objects.none())
    professional = serializers.PrimaryKeyRelatedField(
        queryset=Professional.objects.none(), required=False, allow_null=True
    )
    desired_date = serializers.DateField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        organization = self.context.get("organization")
        if organization:
            self.fields["service"].queryset = Service.objects.filter(
                organization=organization, is_active=True
            )
            self.fields["professional"].queryset = Professional.objects.filter(
                organization=organization, is_active=True
            )

    def validate_name(self, value):
        value = sanitize_free_text(value)
        if len(value) < 2:
            raise serializers.ValidationError("Informe um nome válido.")
        return value

    def validate_phone(self, value):
        if not re.fullmatch(r"\+?[0-9().\-\s]{8,20}", value):
            raise serializers.ValidationError("Informe um telefone válido.")
        has_plus = value.lstrip().startswith("+")
        digits = "".join(character for character in value if character.isdigit())
        if not 8 <= len(digits) <= 15:
            raise serializers.ValidationError("Informe um telefone com 8 a 15 dígitos.")
        return f"+{digits}" if has_plus else digits

    def validate_email(self, value):
        return value.strip().lower()

    def validate_desired_date(self, value):
        organization = self.context["organization"]
        today = timezone.localdate(timezone=ZoneInfo(organization.timezone))
        if value < today:
            raise serializers.ValidationError("A data desejada não pode estar no passado.")
        return value

    def validate_consent(self, value):
        if not value:
            raise serializers.ValidationError("O consentimento é necessário para entrar na lista.")
        return value

    def validate(self, attrs):
        organization = self.context["organization"]
        professional = attrs.get("professional")
        if (
            professional
            and not ProfessionalService.objects.filter(
                organization=organization,
                service=attrs["service"],
                professional=professional,
            ).exists()
        ):
            raise serializers.ValidationError(
                {"professional": "Profissional não oferece este serviço."}
            )
        return attrs


class PublicWaitlistOfferBookSerializer(serializers.Serializer):
    consent = serializers.BooleanField()

    def validate_consent(self, value):
        if not value:
            raise serializers.ValidationError("O consentimento é necessário para reservar.")
        return value
