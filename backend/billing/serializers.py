from rest_framework import serializers

from billing.models import Plan


class PlanSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = Plan
        fields = [
            "id",
            "tier",
            "name",
            "max_professionals",
            "max_appointments_per_month",
            "monthly_price_cents",
        ]

    def get_name(self, obj):
        return obj.nome_para(self.context["organization"])


class CheckoutSerializer(serializers.Serializer):
    tier = serializers.ChoiceField(choices=(("PLUS", "PLUS"), ("PREMIUM", "PREMIUM")))
