import json

from django.conf import settings
from django.http import HttpResponseRedirect
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from billing import selectors, services
from billing.serializers import CheckoutSerializer, PlanSerializer
from core.tenant import resolve_membership
from organizations.models import Membership, Organization


class PlansView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        organization, _ = resolve_membership(request)
        return Response(
            PlanSerializer(
                selectors.list_plans(),
                many=True,
                context={"organization": organization},
            ).data
        )


class UsageView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        organization, _ = resolve_membership(request)
        subscription = services.get_subscription(organization)
        usage = services.monthly_usage(organization)
        return Response(
            {
                "plan": {
                    "tier": subscription.plan.tier,
                    "name": subscription.plan.nome_para(organization),
                },
                "professionals": {
                    "used": usage["professionals"],
                    "limit": subscription.plan.max_professionals,
                },
                "appointments": {
                    "used": usage["appointments"],
                    "limit": subscription.plan.max_appointments_per_month,
                    "period_start": usage["period_start"],
                    "period_end": usage["period_end"],
                },
            }
        )


class CheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        organization, membership = resolve_membership(request)
        if membership.role != Membership.Role.OWNER:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Apenas o proprietário pode iniciar uma assinatura.")
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            services.create_checkout(
                organization=organization, tier=serializer.validated_data["tier"]
            ),
            status=status.HTTP_201_CREATED,
        )


class MercadoPagoConnectView(APIView):
    """OWNER inicia o OAuth da conta Mercado Pago do salão (split de assinatura)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        organization, membership = resolve_membership(request)
        if membership.role != Membership.Role.OWNER:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Apenas o proprietário pode conectar a conta do salão.")
        return Response(
            {
                "authorization_url": services.build_mercadopago_authorization_url(
                    organization=organization
                ),
                "connected": organization.has_mercadopago_seller,
                "seller_id": organization.mercadopago_seller_id,
                "platform_fee_percent": organization.platform_fee_percent,
            }
        )

    def delete(self, request):
        organization, membership = resolve_membership(request)
        if membership.role != Membership.Role.OWNER:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Apenas o proprietário pode desconectar a conta do salão.")
        services.disconnect_mercadopago_seller(organization=organization)
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(csrf_exempt, name="dispatch")
class MercadoPagoCallbackView(APIView):
    """Retorno do Mercado Pago; identifica o salão pelo `state` assinado.

    Sem autenticação: quem chama é o navegador redirecionado pelo Mercado Pago.
    O `state` (HMAC de slug + timestamp, válido por 10 min) é a prova de que o
    fluxo começou nesta plataforma e para este salão.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        slug = request.query_params.get("slug", "")
        code = request.query_params.get("code", "")
        state = request.query_params.get("state", "")
        organization = Organization.objects.filter(slug=slug).first() if slug else None
        base = f"{settings.FRONTEND_URL.rstrip('/')}/app/plano"
        if (
            organization is None
            or not code
            or not services.verify_oauth_state(slug=slug, state=state)
        ):
            return HttpResponseRedirect(f"{base}?mp=erro")
        services.connect_mercadopago_seller(organization=organization, code=code)
        return HttpResponseRedirect(f"{base}?mp=conectado")


@method_decorator(csrf_exempt, name="dispatch")
class MercadoPagoWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(request=None, responses={200: None})
    def post(self, request):
        if not services.verify_webhook_signature(
            body=request.body,
            event_id=request.query_params.get("data.id"),
            signature=request.headers.get("x-signature", ""),
            request_id=request.headers.get("x-request-id", ""),
            secret=settings.MP_WEBHOOK_SECRET,
        ):
            return Response({"detail": "Assinatura inválida."}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            payload = json.loads(request.body)
            result = services.process_webhook(payload)
        except (json.JSONDecodeError, ValueError):
            return Response({"detail": "Payload inválido."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)
