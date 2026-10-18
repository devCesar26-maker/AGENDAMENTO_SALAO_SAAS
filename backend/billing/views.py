import json

from django.conf import settings
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
from organizations.models import Membership


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
            return Response(
                {"detail": "Assinatura inválida."}, status=status.HTTP_401_UNAUTHORIZED
            )
        try:
            payload = json.loads(request.body)
            result = services.process_webhook(payload)
        except (json.JSONDecodeError, ValueError):
            return Response(
                {"detail": "Payload inválido."}, status=status.HTTP_400_BAD_REQUEST
            )
        return Response(result)
