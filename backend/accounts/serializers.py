"""
Serializers de autenticação e perfil (campos sempre explícitos; nunca `__all__`).
"""

from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed

from accounts import services
from core.api.jwt import TenantTokenObtainPairSerializer


class RegisterSerializer(serializers.Serializer):
    """
    Cadastro: o payload nunca define role/organization — o usuário nasce OWNER
    do próprio salão. Erro de e-mail duplicado é genérico (anti-enumeration).
    """

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    organization_name = serializers.CharField(max_length=120)
    vertical = serializers.ChoiceField(choices=("SALAO", "BARBEARIA"))
    organization_phone = serializers.CharField(required=False, allow_blank=True, max_length=20)

    def validate_email(self, value: str) -> str:
        from django.contrib.auth import get_user_model

        if get_user_model().objects.filter(email=value.strip().lower()).exists():
            # Mensagem deliberadamente genérica: não revela se o e-mail existe.
            raise serializers.ValidationError(
                "Não foi possível concluir o cadastro. Verifique os dados informados."
            )
        return value.strip().lower()

    def validate_password(self, value: str) -> str:
        from django.contrib.auth.password_validation import validate_password

        validate_password(value)
        return value

    def save(self, **kwargs):
        return services.register_with_organization(**self.validated_data)


class LoginSerializer(TenantTokenObtainPairSerializer):
    """
    Login por e-mail com bloqueio temporário: após N falhas para o mesmo
    e-mail, novas tentativas recebem 429 até a janela expirar.
    """

    default_error_messages = {
        "no_active_account": "Credenciais inválidas. Verifique e-mail e senha."
    }

    def validate(self, attrs):
        raw_email = str(attrs.get(self.username_field) or "").strip().lower()

        wait = services.check_login_allowed(raw_email)
        if wait is not None:
            from rest_framework.exceptions import Throttled

            raise Throttled(
                detail=f"Muitas tentativas de login. Tente novamente em {wait} s.",
                wait=int(wait),
            )

        try:
            data = super().validate(attrs)
        except (AuthenticationFailed, serializers.ValidationError):
            services.register_failed_login(raw_email)
            raise
        services.clear_login_failures(raw_email)
        return data


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(write_only=True)

    def save(self):
        services.blacklist_refresh(self.validated_data["refresh"])


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value: str) -> str:
        return value.strip().lower()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uidb64 = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def _resolve_user(self):
        """Usuário do link (uid) OU None; token validado onde o user existe."""
        from django.contrib.auth import get_user_model
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import DjangoUnicodeDecodeError, force_str
        from django.utils.http import urlsafe_base64_decode

        User = get_user_model()
        try:
            user_id = force_str(urlsafe_base64_decode(self.initial_data.get("uidb64", "")))
            user = User.objects.get(pk=user_id)
        except (User.DoesNotExist, ValueError, DjangoUnicodeDecodeError, TypeError):
            return None
        if not default_token_generator.check_token(user, self.initial_data.get("token", "")):
            return None
        return user

    def validate(self, attrs):
        self.user = self._resolve_user()
        if self.user is None:
            raise serializers.ValidationError(
                {"detail": ["Link inválido ou expirado. Solicite um novo."]}
            )
        from django.contrib.auth import password_validation

        password_validation.validate_password(attrs["password"], user=self.user)
        return attrs

    def save(self):
        self.user.set_password(self.validated_data["password"])
        self.user.save(update_fields=["password"])
        return self.user


class MeSerializer(serializers.Serializer):
    """GET /api/v1/me: perfil + salões/memberships ativas do usuário."""

    id = serializers.IntegerField()
    email = serializers.EmailField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    phone = serializers.CharField()
    date_joined = serializers.DateTimeField()
    memberships = serializers.SerializerMethodField()

    def get_memberships(self, user) -> list[dict]:
        from organizations.serializers import MemberOrganizationSerializer

        return [
            {
                "id": membership.id,
                "organization": MemberOrganizationSerializer(membership.organization).data,
                "role": membership.role,
                "is_active": membership.is_active,
                "created_at": membership.created_at,
            }
            for membership in self._prefetched(user)
        ]

    def _prefetched(self, user):
        if (
            hasattr(user, "_prefetched_objects_cache")
            and "memberships" in user._prefetched_objects_cache
        ):
            return list(user._prefetched_objects_cache["memberships"])
        return list(user.memberships.filter(is_active=True).select_related("user", "organization"))
