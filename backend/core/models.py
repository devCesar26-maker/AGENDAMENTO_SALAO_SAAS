"""
Modelos base compartilhados por todos os apps de domínio.
"""

from datetime import timedelta

from django.db import models
from django.utils import timezone


def default_idempotency_expiry():
    return timezone.now() + timedelta(hours=48)


class TimeStampedModel(models.Model):
    """Base abstrata com auditoria de criação/alteração."""

    created_at = models.DateTimeField("criado em", auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        abstract = True


class TenantScopedQuerySet(models.QuerySet):
    """
    QuerySet reutilizável para entidades de negócio (todas com FK `organization`).

    O isolamento multi-tenant é aplicado de forma EXPLÍCITA, em dois pontos:

    1. Queries de domínio chamam `for_tenant(organization)` (ou `for_user(user)`);
    2. Endpoints usam `TenantModelViewSet` (core.tenant), que resolve o tenant
       a partir da Membership do usuário autenticado e filtra automaticamente —
       nunca de parâmetros de URL/payload.

    Não usamos thread-local no manager: contextos sem request (Celery, admin,
    commands) e servidores async tornam esse padrão propenso a vazamento entre
    requisições. Aqui, todo queryset de negócio é escopado explicitamente.
    """

    def for_tenant(self, organization):
        """Registros pertencentes apenas à organização (tenant) informada."""
        return self.filter(organization=organization)

    def for_user(self, user):
        """Registros das organizações em que o usuário tem membership ativa."""
        org_ids = user.memberships.filter(is_active=True).values_list(
            "organization_id", flat=True
        )
        return self.filter(organization_id__in=org_ids)


TenantScopedManager = models.Manager.from_queryset(TenantScopedQuerySet)


class TenantModel(TimeStampedModel):
    """
    Base abstrata para entidades de negócio de um salão (tenant).

    Herde esta classe em toda entidade futura (serviços, agendamentos, clientes
    etc.) e use `TenantScopedQuerySet`/`TenantModelViewSet` para o scoping.
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
        verbose_name="salão",
    )

    objects = TenantScopedManager()

    class Meta:
        abstract = True


class IdempotencyKey(models.Model):
    """Durable deduplication record scoped by tenant, context and client key."""

    class State(models.TextChoices):
        PROCESSING = "PROCESSING", "Em processamento"
        COMPLETED = "COMPLETED", "Concluída"

    key = models.CharField(max_length=255, db_index=True)
    scope_digest = models.CharField(max_length=64, unique=True)
    organization = models.ForeignKey(
        "organizations.Organization",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="idempotency_keys",
    )
    context = models.CharField(max_length=80)
    request_fingerprint = models.CharField(max_length=64)
    state = models.CharField(
        max_length=12, choices=State.choices, default=State.PROCESSING
    )
    result = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField(default=default_idempotency_expiry, db_index=True)

    class Meta:
        indexes = [
            models.Index(
                fields=("context", "expires_at"), name="idempotency_expiry_idx"
            )
        ]

    def __str__(self):
        return f"{self.context}:{self.key}"
