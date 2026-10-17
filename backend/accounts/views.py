"""
Endpoints de autenticação e perfil (views finas; regras em services.py).
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from accounts import serializers, services
from accounts.models import User
from core.api.jwt import TenantTokenObtainPairSerializer, tenant_user_payload
from core.api.throttling import AuthRateThrottle


def set_refresh_cookie(response, token):
    response.set_cookie(
        settings.REFRESH_TOKEN_COOKIE_NAME,
        token,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        httponly=True,
        secure=settings.REFRESH_TOKEN_COOKIE_SECURE,
        samesite=settings.REFRESH_TOKEN_COOKIE_SAMESITE,
        path=settings.REFRESH_TOKEN_COOKIE_PATH,
        domain=settings.REFRESH_TOKEN_COOKIE_DOMAIN,
    )


def clear_refresh_cookie(response):
    response.delete_cookie(
        settings.REFRESH_TOKEN_COOKIE_NAME,
        path=settings.REFRESH_TOKEN_COOKIE_PATH,
        domain=settings.REFRESH_TOKEN_COOKIE_DOMAIN,
        samesite=settings.REFRESH_TOKEN_COOKIE_SAMESITE,
    )


# Views de obtenção/renovação de JWT (rotação + blacklist habilitadas na config).
# SimpleJWT não aplica throttle por padrão — fazemos isso explicitamente aqui.
class LoginView(TokenObtainPairView):
    throttle_classes = [AuthRateThrottle]
    throttle_scope = "auth"

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK and "refresh" in response.data:
            refresh = response.data.pop("refresh")
            set_refresh_cookie(response, refresh)
        return response


class RefreshTokenView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        data = request.data.copy()
        data.setdefault("refresh", request.COOKIES.get(settings.REFRESH_TOKEN_COOKIE_NAME, ""))
        serializer = self.get_serializer(data=data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise InvalidToken(exc.args[0]) from exc
        response_data = serializer.validated_data
        refresh = response_data.pop("refresh", None)
        access = response_data.get("access")
        if access:
            user_id = AccessToken(access).get("user_id")
            user = get_user_model().objects.filter(pk=user_id).first()
            if user:
                response_data["user"] = tenant_user_payload(user)
        response = Response(response_data, status=status.HTTP_200_OK)
        if refresh:
            set_refresh_cookie(response, refresh)
        return response


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
        data = request.data.copy()
        data.setdefault("refresh", request.COOKIES.get(settings.REFRESH_TOKEN_COOKIE_NAME, ""))
        logout_serializer = serializers.LogoutSerializer(data=data)
        logout_serializer.is_valid(raise_exception=True)
        logout_serializer.save()
        response = Response({"detail": "Logout realizado com sucesso."}, status=status.HTTP_200_OK)
        clear_refresh_cookie(response)
        return response


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
