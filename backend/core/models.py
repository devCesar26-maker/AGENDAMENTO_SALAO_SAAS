"""Modelos base compartilhados por todos os apps de domínio."""

from django.db import models


class TimeStampedModel(models.Model):
    """Base abstrata com auditoria de criação/alteração."""

    created_at = models.DateTimeField("criado em", auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        abstract = True


class TenantModel(TimeStampedModel):
    """
    Base abstrata para entidades de negócio de um salão (tenant).

    Toda consulta de negócio deve passar por `for_tenant(organization)` ou pelo
    mixin `TenantModelViewSet`, que resolve o tenant a partir da Membership do
    usuário autenticado — nunca de parâmetros do cliente (ver core.tenant).
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
        verbose_name="salão",
    )

    class Meta:
        abstract = True
