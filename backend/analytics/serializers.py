"""Serializers de query params e respostas públicas de analytics."""

from rest_framework import serializers

from analytics.models import AuditLog
from scheduling.models import Appointment


class PeriodQuerySerializer(serializers.Serializer):
    data_inicio = serializers.DateField(required=False)
    data_fim = serializers.DateField(required=False)

    def validate(self, attrs):
        if (
            attrs.get("data_inicio")
            and attrs.get("data_fim")
            and attrs["data_fim"] < attrs["data_inicio"]
        ):
            raise serializers.ValidationError(
                {"data_fim": "A data final deve ser igual ou posterior à inicial."}
            )
        return attrs


class AppointmentExportQuerySerializer(PeriodQuerySerializer):
    status = serializers.ChoiceField(choices=Appointment.Status.choices, required=False)
    profissional = serializers.IntegerField(min_value=1, required=False)


class OverviewSerializer(serializers.Serializer):
    total_appointments = serializers.IntegerField()
    occupancy_rate = serializers.FloatField()
    no_show_rate = serializers.FloatField()
    estimated_revenue = serializers.DecimalField(max_digits=14, decimal_places=2)


class ServiceMetricSerializer(serializers.Serializer):
    service_id = serializers.IntegerField()
    service_name = serializers.CharField()
    quantity = serializers.IntegerField()
    revenue = serializers.DecimalField(max_digits=14, decimal_places=2)


class ProfessionalMetricSerializer(serializers.Serializer):
    professional_id = serializers.IntegerField()
    professional_name = serializers.CharField()
    appointments = serializers.IntegerField()
    revenue = serializers.DecimalField(max_digits=14, decimal_places=2)


class AuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "action",
            "actor",
            "actor_name",
            "object_type",
            "object_id",
            "context",
            "created_at",
        ]
        read_only_fields = fields

    def get_actor_name(self, obj):
        if obj.actor_id is None:
            return None
        return obj.actor.user.get_full_name() or obj.actor.user.email
