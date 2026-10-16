"""
Endpoints de autenticação e perfil (views finas; regras em services.py).
"""

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from accounts import serializers, services
from accounts.models import User
from core.api.jwt import TenantTokenObtainPairSerializer
from core.api.throttling import AuthRateThrottle


# Views de obtenção/renovação de JWT (rotação + blacklist habilitadas na config).
# SimpleJWT não aplica throttle por padrão — fazemos isso explicitamente aqui.
class LoginView(TokenObtainPairView):
    throttle_classes = [AuthRateThrottle]
    throttle_scope = "auth"


class RefreshTokenView(TokenRefreshView):
    pass  # não throttlea para não quebrar evitação de relogio do 401 do refresh


class RegisterView(APIView):
    """POST /api/v1/auth/register/ — público, com throttle e transação atômica."""

    authentication_classes: list = []
    permission_classes: list = []
    throttle_classes = [AuthRateThrottle]
    throttle_scope = "auth"

    @extend_schema(
        request=serializers.RegisterSerializer,
        responses={201: dict},
        summary="Cria usuário + salão + membership OWNER",
        tags=["auth"],
    )
    def post(self, request):
        serializer = serializers.RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, organization = serializer.save()
        tokens = TenantTokenObtainPairSerializer.get_token(user)
        data = {
            "access": str(tokens.access_token),
            "refresh": str(tokens),
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
            },
            "organization": {
                "id": organization.id,
                "name": organization.name,
                "slug": organization.slug,
                "vertical": organization.vertical,
                "tema_cor": organization.tema_cor,
            },
        }
        return Response(data, status=status.HTTP_201_CREATED)


class LogoutView(APIView):
    """POST /api/v1/auth/logout/ — blacklista o refresh token recebido."""

    throttle_classes = [AuthRateThrottle]
    throttle_scope = "auth"

    @extend_schema(
        request=serializers.LogoutSerializer,
        responses={200: dict},
        summary="Invalida refresh token (blacklist)",
        tags=["auth"],
    )
    def post(self, request):
        logout_serializer = serializers.LogoutSerializer(data=request.data)
        logout_serializer.is_valid(raise_exception=True)
        logout_serializer.save()
        return Response({"detail": "Logout realizado com sucesso."}, status=status.HTTP_200_OK)


class PasswordResetRequestView(APIView):
    """POST público — resposta idêntica exista ou não o e-mail no sistema."""

    authentication_classes: list = []
    permission_classes: list = []
    throttle_classes = [AuthRateThrottle]
    throttle_scope = "auth"

    @extend_schema(
        request=serializers.PasswordResetRequestSerializer,
        responses={200: dict},
        summary="Solicita reset de senha (resposta idêntica para e-mail existente ou não)",
        tags=["auth"],
    )
    def post(self, request):
        serializer = serializers.PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.request_password_reset(serializer.validated_data["email"])
        return Response(
            {
                "detail": "Se este e-mail estiver cadastrado, você receberá um link de redefinição em instantes."
            },
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(APIView):
    """POST público — define nova senha a partir de uidb64 + token do e-mail."""

    authentication_classes: list = []
    permission_classes: list = []
    throttle_classes = [AuthRateThrottle]
    throttle_scope = "auth"

    @extend_schema(
        request=serializers.PasswordResetConfirmSerializer,
        responses={200: dict},
        summary="Confirma reset de senha com uidb64 + token",
        tags=["auth"],
    )
    def post(self, request):
        serializer = serializers.PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Senha redefinida com sucesso."}, status=status.HTTP_200_OK)


class MeView(APIView):
    """GET /api/v1/me — perfil + salões/memberships do usuário autenticado."""

    @extend_schema(
        responses={200: serializers.MeSerializer},
        summary="Perfil e memberships do usuário autenticado",
        tags=["auth"],
    )
    def get(self, request):
        from django.db.models import Prefetch

        from organizations.models import Membership

        user = (
            User.objects.filter(pk=request.user.pk)
            .prefetch_related(
                Prefetch(
                    "memberships",
                    queryset=Membership.objects.filter(is_active=True).select_related(
                        "user", "organization"
                    ),
                )
            )
            .get(pk=request.user.pk)
        )
        return Response(serializers.MeSerializer(user).data)
