"""
Serializers do catálogo: campos SEMPRE explícitos, `organization` nunca vem
do payload (injetado por `TenantModelViewSet.perform_create`), validação de
integridade entre tenants e sanitização de texto livre.
"""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from catalog.models import (
    Professional,
    ProfessionalService,
    Service,
    ServiceCategory,
    TimeOff,
    WorkingHours,
)
from core.sanitization import sanitize_free_text
from organizations.models import Membership

# Campos que um pro profissional pode alterar no PRÓPRIO perfil (dados básicos);
# `user` e `is_active` são decisões do OWNER/MANAGER.
_CAMPOS_DO_PROFISSIONAL = {"name", "photo"}


class ServiceCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceCategory
        fields = ["id", "name", "order", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_name(self, value: str) -> str:
        """Nome único por salão (tradução amigável da constraint do banco)."""
        organization = self.context.get("organization")
        cleaned = sanitize_free_text(value).strip()
        qs = ServiceCategory.objects.filter(organization=organization, name__iexact=cleaned)
        instance_pk = getattr(self.instance, "pk", None)
        if instance_pk is not None:
            qs = qs.exclude(pk=instance_pk)
        if qs.exists():
            raise serializers.ValidationError("Já existe uma categoria com este nome neste salão.")
        return cleaned


class ServiceSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Service
        fields = [
            "id",
            "category",
            "category_name",
            "name",
            "description",
            "duration_minutes",
            "price",
            "buffer_minutes",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "category_name", "created_at", "updated_at"]

    def validate_name(self, value: str) -> str:
        return sanitize_free_text(value)

    def validate_description(self, value: str) -> str:
        return sanitize_free_text(value)

    def validate_category(self, category: ServiceCategory) -> ServiceCategory:
        """IDOR via FK: a categoria precisa pertencer ao mesmo salão."""
        organization = self.context.get("organization")
        if organization is not None and category.organization_id != organization.id:
            raise serializers.ValidationError("Categoria não pertence a este salão.")
        return category


class ServiceLinkReadSerializer(serializers.ModelSerializer):
    """Vínculo profissional ↔ serviço (leitura, com dados mínimos do serviço)."""

    service = serializers.PrimaryKeyRelatedField(read_only=True)
    service_name = serializers.CharField(source="service.name", read_only=True)
    service_category = serializers.CharField(source="service.category.name", read_only=True)

    class Meta:
        model = ProfessionalService
        fields = [
            "id",
            "service",
            "service_name",
            "service_category",
            "price_override",
            "duration_override",
            "commission_percentage",
        ]


class ProfessionalUserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.EmailField()


class ProfessionalSerializer(serializers.ModelSerializer):
    """Leitura do profissional, incluindo serviços vinculados (sem N+1)."""

    user = ProfessionalUserSerializer(allow_null=True, read_only=True)
    service_links = ServiceLinkReadSerializer(many=True, read_only=True)

    class Meta:
        model = Professional
        fields = [
            "id",
            "user",
            "name",
            "photo",
            "is_active",
            "service_links",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ProfessionalWriteSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.all(), allow_null=True, required=False
    )

    class Meta:
        model = Professional
        fields = ["id", "user", "name", "photo", "is_active"]
        read_only_fields = ["id"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # PROFESSIONAL só altera os próprios dados básicos (regra da Fase 2).
        if self.context.get("role") == Membership.Role.PROFESSIONAL:
            self.fields.pop("user", None)
            self.fields["is_active"].read_only = True

    def validate_name(self, value: str) -> str:
        return sanitize_free_text(value)

    def validate_user(self, user) -> object | None:
        """
        Anti-escalonamento: o usuário vinculado precisa ser membro ATIVO do
        mesmo salão e não pode já estar vinculado a outro profissional.
        """
        organization = self.context.get("organization")
        if user is None:
            return user
        if (
            organization is not None
            and not user.memberships.filter(organization=organization, is_active=True).exists()
        ):
            raise serializers.ValidationError(
                "O usuário vinculado precisa ser membro ativo deste salão."
            )
        qs = Professional.objects.filter(organization=organization, user=user)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "Este usuário já está vinculado a outro profissional do salão."
            )
        return user


class ProfessionalLinkWriteSerializer(serializers.ModelSerializer):
    """POST do vínculo serviço: o `professional` vem da URL, nunca do payload."""

    professional = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = ProfessionalService
        fields = [
            "id",
            "professional",
            "service",
            "price_override",
            "duration_override",
            "commission_percentage",
        ]
        read_only_fields = ["id", "professional"]


class ProfessionalLinkUpdateSerializer(serializers.ModelSerializer):
    """PATCH do vínculo: ajusta apenas overrides/comissão."""

    class Meta:
        model = ProfessionalService
        fields = ["price_override", "duration_override", "commission_percentage"]


class WorkingHoursSerializer(serializers.ModelSerializer):
    professional = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = WorkingHours
        fields = ["id", "professional", "weekday", "start_time", "end_time"]
        read_only_fields = ["id", "professional"]

    def validate(self, attrs):
        # PATCH parcial: complementa com os valores persistidos antes de validar.
        start = attrs.get("start_time", getattr(self.instance, "start_time", None))
        end = attrs.get("end_time", getattr(self.instance, "end_time", None))
        if start is not None and end is not None and start == end:
            raise serializers.ValidationError(
                {"end_time": "O início e o término não podem ser iguais."}
            )
        return attrs


class TimeOffSerializer(serializers.ModelSerializer):
    professional = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = TimeOff
        fields = ["id", "professional", "start_date", "end_date", "reason"]
        read_only_fields = ["id", "professional"]

    def validate_reason(self, value: str) -> str:
        return sanitize_free_text(value)

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start is not None and end is not None and end < start:
            raise serializers.ValidationError(
                {"end_date": "A data fim deve ser igual ou posterior à data início."}
            )
        return attrs
