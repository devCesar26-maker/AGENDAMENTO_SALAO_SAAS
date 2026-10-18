"""
Serializers de clientes: campos explícitos, `organization` nunca do payload,
normalização de e-mail/telefone e sanitização das observações (texto simples).
"""

from rest_framework import serializers

from core.sanitization import sanitize_free_text

from .models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = [
            "id",
            "name",
            "phone",
            "email",
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
        if not cleaned.strip():
            raise serializers.ValidationError("Informe um telefone válido.")
        return cleaned

    def validate_email(self, value: str) -> str:
        cleaned = value.strip().lower()
        return cleaned

    def validate_notes(self, value: str) -> str:
        return sanitize_free_text(value)


class LgpdConsentSerializer(serializers.Serializer):
    """Payload do endpoint de consentimento: booleano obrigatório."""

    consented = serializers.BooleanField()
