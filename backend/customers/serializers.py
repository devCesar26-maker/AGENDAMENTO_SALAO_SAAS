"""
Serializers de clientes: campos explícitos, `organization` nunca do payload,
normalização de e-mail/telefone e sanitização das observações (texto simples).
"""

from rest_framework import serializers

from core.sanitization import sanitize_free_text

from .models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    responsavel = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = Customer
        fields = [
            "id",
            "name",
            "phone",
            "email",
            "responsavel",
            "notes",
            "birthday",
            "lgpd_consent",
            "lgpd_consent_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "lgpd_consent",
            "lgpd_consent_at",
            "created_at",
            "updated_at",
        ]

    def validate_name(self, value: str) -> str:
        return sanitize_free_text(value)

    def validate_phone(self, value: str) -> str:
        cleaned = sanitize_free_text(value)
        return cleaned

    def validate_responsavel(self, value):
        organization = self.context.get("organization")
        if value is None:
            return value
        if organization and value.organization_id != organization.pk:
            raise serializers.ValidationError("Responsável não pertence a esta organização.")
        if self.instance and value.pk == self.instance.pk:
            raise serializers.ValidationError("Um cliente não pode ser responsável de si mesmo.")
        if value.responsavel_id:
            raise serializers.ValidationError("Não são permitidas cadeias de responsáveis.")
        if self.instance and self.instance.dependentes.exists():
            raise serializers.ValidationError(
                "Um responsável com dependentes não pode ser dependente."
            )
        return value

    def validate(self, attrs):
        responsible = attrs.get("responsavel", getattr(self.instance, "responsavel", None))
        phone = attrs.get("phone", getattr(self.instance, "phone", ""))
        if not responsible and not phone.strip():
            raise serializers.ValidationError(
                {"phone": "Informe um telefone para clientes sem responsável."}
            )
        return attrs

    def validate_email(self, value: str) -> str:
        cleaned = value.strip().lower()
        return cleaned

    def validate_notes(self, value: str) -> str:
        return sanitize_free_text(value)


class LgpdConsentSerializer(serializers.Serializer):
    """Payload do endpoint de consentimento: booleano obrigatório."""

    consented = serializers.BooleanField()
