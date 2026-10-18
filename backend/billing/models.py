"""Planos e estado de cobrança por organização."""

from django.db import models

from core.models import TimeStampedModel


class PlanTier(models.TextChoices):
    FREE = "FREE", "Free"
    PLUS = "PLUS", "Plus"
    PREMIUM = "PREMIUM", "Premium"


class SubscriptionStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Ativa"
    PAST_DUE = "PAST_DUE", "Pagamento pendente"
    CANCELED = "CANCELED", "Cancelada"
    TRIALING = "TRIALING", "Em teste"


class Plan(TimeStampedModel):
    tier = models.CharField(max_length=10, choices=PlanTier.choices, unique=True)
    nome_salao = models.CharField(max_length=80)
    nome_barbearia = models.CharField(max_length=80)
    max_professionals = models.PositiveIntegerField(null=True, blank=True)
    max_appointments_per_month = models.PositiveIntegerField(null=True, blank=True)
    monthly_price_cents = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["monthly_price_cents"]

    def nome_para(self, organization):
        from organizations.models import Organization

        return (
            self.nome_barbearia
            if organization.vertical == Organization.Vertical.BARBEARIA
            else self.nome_salao
        )


class Subscription(TimeStampedModel):
    organization = models.OneToOneField(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="subscription",
    )
    plan = models.ForeignKey(
        Plan, on_delete=models.PROTECT, related_name="subscriptions"
    )
    status = models.CharField(
        max_length=12,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.ACTIVE,
    )
    mercadopago_subscription_id = models.CharField(
        max_length=120, blank=True, default=""
    )
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(
        "fim do período atual", null=True, blank=True
    )

    class Meta:
        verbose_name = "assinatura"
        verbose_name_plural = "assinaturas"

    @property
    def limits(self):
        return {
            "max_professionals": self.plan.max_professionals,
            "max_appointments_per_month": self.plan.max_appointments_per_month,
        }
