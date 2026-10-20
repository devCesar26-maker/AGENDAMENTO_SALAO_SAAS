"""
Serializers de salões, membros e convites (campos sempre explícitos).
"""

from rest_framework import serializers

from organizations import services
from organizations.models import Invitation, Membership, Organization


class OrganizationSerializer(serializers.ModelSerializer):
    """Detalhe/edição do salão. `slug` é gerado se omitido e editável via PATCH."""

    working_hours = serializers.JSONField(
        required=False, validators=[services.validar_working_hours]
    )

    class Meta:
        model = Organization
        fields = [
            "id",
            "name",
            "slug",
            "vertical",
            "tema_cor",
            "timezone",
            "phone",
            "address",
            "working_hours",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "created_at", "vertical", "tema_cor"]

    def validate_slug(self, value: str) -> str:
        """Slug editável, mas sempre único (case-sensitive baixo: slugify já minúsculas)."""
        qs = Organization.objects.filter(slug__iexact=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Já existe um salão com este slug.")
        return value


class MemberUserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.EmailField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()


class MemberOrganizationSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    slug = serializers.SlugField()


class MemberSerializer(serializers.ModelSerializer):
    """Membro do salão: WRITE apenas em role/is_active e sempre via service (OWNER)."""

    user = MemberUserSerializer(read_only=True)
    organization = MemberOrganizationSerializer(read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "user", "organization", "role", "is_active", "created_at"]
        read_only_fields = ["id", "user", "organization", "created_at"]


class InvitationCreateSerializer(serializers.ModelSerializer):
    """Payload de convite: e-mail + role apenas. O salão vem da URL autenticada."""

    email = serializers.EmailField()

    class Meta:
        model = Invitation
        fields = ["email", "role"]

    def validate_role(self, value: str) -> str:
        if value == Membership.Role.OWNER:
            raise serializers.ValidationError(
                "Convites não podem conceder o papel de proprietário."
            )
        return value


class InvitationSerializer(serializers.ModelSerializer):
    """Convite pendente, incluindo token/link (visível só a OWNER/MANAGER)."""

    invite_url = serializers.SerializerMethodField()
    invited_by_email = serializers.CharField(
        source="invited_by.email", read_only=True, default=None
    )

    class Meta:
        model = Invitation
        fields = [
            "id",
            "email",
            "role",
            "token",
            "invite_url",
            "invited_by_email",
            "accepted_at",
            "expires_at",
            "created_at",
        ]
        read_only_fields = fields

    def get_invite_url(self, invitation: Invitation) -> str:
        from django.conf import settings

        return f"{settings.FRONTEND_URL.rstrip('/')}/convite/{invitation.token}"


class InvitationAcceptSerializer(serializers.Serializer):
    """
    Aceite de convite. role/sub quiserem? Não: role SEMPRE vem do Invitation
    (anti-escalation); aqui só dados de criação de conta quando o e-mail é novo.
    """

    password = serializers.CharField(
        write_only=True, required=False, style={"input_type": "password"}
    )
    first_name = serializers.CharField(required=False, max_length=150)
    last_name = serializers.CharField(required=False, max_length=150)
