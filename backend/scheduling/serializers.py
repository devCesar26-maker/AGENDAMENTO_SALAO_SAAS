"""Serializers explícitos para disponibilidade e agendamentos."""

import re

from rest_framework import serializers

from catalog.models import Professional, ProfessionalService, Service
from core.sanitization import sanitize_free_text
from customers.models import Customer
from scheduling.models import Appointment, AppointmentItem


class AvailabilityQuerySerializer(serializers.Serializer):
    MAX_SERVICES = 5
    services = serializers.CharField()
    professional = serializers.CharField()
    date = serializers.DateField()

    def validate_services(self, value):
        if len(value) > 64:
            raise serializers.ValidationError(
                "Informe no máximo cinco serviços por reserva."
            )
        try:
            ids = [int(pk) for pk in value.split(",")]
        except ValueError as exc:
            raise serializers.ValidationError(
                "Use uma lista de IDs separados por vírgula."
            ) from exc
        if not ids or any(pk < 1 for pk in ids) or len(ids) != len(set(ids)):
            raise serializers.ValidationError(
                "Informe IDs de serviços válidos e sem repetição."
            )
        if len(ids) > self.MAX_SERVICES:
            raise serializers.ValidationError(
                f"Escolha no máximo {self.MAX_SERVICES} serviços por reserva."
            )
        return ids

    def validate_professional(self, value):
        if value.lower() == "any":
            return None
        try:
            pk = int(value)
        except ValueError as exc:
            raise serializers.ValidationError(
                "Informe um ID de profissional ou 'any'."
            ) from exc
        if pk < 1:
            raise serializers.ValidationError("ID de profissional inválido.")
        return pk


class AvailabilityItemResponseSerializer(serializers.Serializer):
    service = serializers.IntegerField()
    professional = serializers.IntegerField()
    start_at = serializers.DateTimeField()
    end_at = serializers.DateTimeField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    commission_percentage = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False
    )


class AvailabilitySlotResponseSerializer(serializers.Serializer):
    start_at = serializers.DateTimeField()
    items = AvailabilityItemResponseSerializer(many=True)


class AvailabilityResponseSerializer(serializers.Serializer):
    date = serializers.DateField()
    timezone = serializers.CharField()
    slots = AvailabilitySlotResponseSerializer(many=True)


class AppointmentItemInputSerializer(serializers.Serializer):
    service = serializers.PrimaryKeyRelatedField(queryset=Service.objects.all())
    professional = serializers.PrimaryKeyRelatedField(
        queryset=Professional.objects.all()
    )
    order = serializers.IntegerField(min_value=0)


class AppointmentCreateSerializer(serializers.Serializer):
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all())
    items = AppointmentItemInputSerializer(many=True, allow_empty=False, max_length=5)
    start_at = serializers.DateTimeField()
    notes = serializers.CharField(required=False, allow_blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        organization = self.context.get("organization")
        if organization is not None:
            self.fields["customer"].queryset = Customer.objects.filter(
                organization=organization
            )
            self.fields["items"].child.fields["service"].queryset = (
                Service.objects.filter(organization=organization)
            )
            self.fields["items"].child.fields["professional"].queryset = (
                Professional.objects.filter(organization=organization)
            )

    def validate_customer(self, customer):
        if customer.organization_id != self.context["organization"].id:
            raise serializers.ValidationError(
                "Cliente não pertence a esta organização."
            )
        return customer

    def validate_items(self, items):
        organization = self.context["organization"]
        if len({item["order"] for item in items}) != len(items):
            raise serializers.ValidationError("A ordem dos itens não pode se repetir.")
        pairs = set()
        for item in items:
            if item["service"].organization_id != organization.id:
                raise serializers.ValidationError(
                    "Serviço não pertence a esta organização."
                )
            if item["professional"].organization_id != organization.id:
                raise serializers.ValidationError(
                    "Profissional não pertence a esta organização."
                )
            if not item["service"].is_active or not item["professional"].is_active:
                raise serializers.ValidationError(
                    "Serviço e profissional precisam estar ativos."
                )
            pairs.add((item["service"].pk, item["professional"].pk))
        links = set(
            ProfessionalService.objects.filter(
                organization=organization,
                service_id__in={service_id for service_id, _ in pairs},
                professional_id__in={professional_id for _, professional_id in pairs},
            ).values_list("service_id", "professional_id")
        )
        if not pairs.issubset(links):
            raise serializers.ValidationError(
                "Cada profissional precisa estar vinculado ao serviço correspondente."
            )
        return sorted(items, key=lambda item: item["order"])

    def validate_notes(self, value):
        return sanitize_free_text(value)


class PublicAppointmentCreateSerializer(serializers.Serializer):
    """Entrada pública: identificação do cliente, consentimento e serviços."""

    name = serializers.CharField(max_length=120, trim_whitespace=True)
    phone = serializers.CharField(max_length=20, trim_whitespace=True)
    email = serializers.EmailField(max_length=254, required=False, allow_blank=True)
    consent = serializers.BooleanField()
    items = AppointmentItemInputSerializer(many=True, allow_empty=False, max_length=5)
    start_at = serializers.DateTimeField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        organization = self.context.get("organization")
        if organization is not None:
            self.fields["items"].child.fields["service"].queryset = (
                Service.objects.filter(organization=organization)
            )
            self.fields["items"].child.fields["professional"].queryset = (
                Professional.objects.filter(organization=organization)
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

    def validate_consent(self, value):
        if not value:
            raise serializers.ValidationError(
                "O consentimento é necessário para reservar."
            )
        return value

    def validate_items(self, items):
        if len({item["order"] for item in items}) != len(items):
            raise serializers.ValidationError(
                "A ordem dos serviços não pode se repetir."
            )
        return sorted(items, key=lambda item: item["order"])


class AppointmentItemSerializer(serializers.ModelSerializer):
    service_name = serializers.CharField(source="service.name", read_only=True)
    professional_name = serializers.CharField(
        source="professional.name", read_only=True
    )

    class Meta:
        model = AppointmentItem
        fields = [
            "id",
            "service",
            "service_name",
            "professional",
            "professional_name",
            "order",
            "start_at",
            "end_at",
            "buffer_minutes",
            "price",
            "commission_percentage",
        ]


class AppointmentSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    items = AppointmentItemSerializer(many=True, read_only=True)

    class Meta:
        model = Appointment
        fields = [
            "id",
            "customer",
            "customer_name",
            "status",
            "origin",
            "created_by",
            "notes",
            "items",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class AppointmentStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Appointment.Status.choices)


class AppointmentRescheduleSerializer(serializers.Serializer):
    start_at = serializers.DateTimeField()
