"""Modelos de cobrança: Plan e Subscription (Fase 6 adiciona Stripe)."""

from django.db import models

from core.models import TimeStampedModel


class Plan(models.TextChoices):
    FREE = "FREE", "Grátis"
    PRO = "PRO", "Pro"


class Subscription(TimeStampedModel):
    """Estado da assinatura do salão. Salões novos nascem FREE (ver signals)."""

    organization = models.OneToOneField(
        "organizations.Organization", on_delete=models.CASCADE, related_name="subscription"
    )
    plan = models.CharField("plano", max_length=10, choices=Plan.choices, default=Plan.FREE)
    is_active = models.BooleanField("ativa", default=True)
    provider = models.CharField("provedor", max_length=20, blank=True, default="")
    provider_customer_id = models.CharField(
        "id do cliente no provedor", max_length=120, blank=True, default=""
    )
    provider_subscription_id = models.CharField(
        "id da assinatura no provedor", max_length=120, blank=True, default=""
    )
    current_period_end = models.DateTimeField("fim do período atual", null=True, blank=True)

    class Meta:
        verbose_name = "assinatura"
        verbose_name_plural = "assinaturas"

    def __str__(self) -> str:
        return f"{self.organization}: {self.plan}"

    @property
    def limits(self) -> dict:
        from django.conf import settings

        return settings.PLAN_LIMITS.get(self.plan, {})
