"""Healthcheck para Docker/K8s/load balancers."""

from typing import ClassVar

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthSerializer(serializers.Serializer):
    status = serializers.CharField()
    servico = serializers.CharField()


class HealthView(APIView):
    permission_classes: ClassVar[list] = [AllowAny]
    authentication_classes: ClassVar[list] = []

    @extend_schema(responses={200: HealthSerializer}, tags=["Infra"])
    def get(self, request):
        return Response({"status": "ok", "servico": "ecalt-studio"})
