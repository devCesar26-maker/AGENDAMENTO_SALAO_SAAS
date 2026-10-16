"""
Clientes do salão (CRM simples) — dados pessoais com consentimento LGPD.

Inclui o cliente no padrão de tenant: herda `TenantModel` e é escopada
explicitamente (`for_tenant`) em selectors/views; o `organization_id` nunca
vem do payload.
"""

from django.db import models

from core.models import TenantModel


class Customer(TenantModel):
    """Cliente cadastrado pelo salão (nome e telefone obrigatórios)."""

    name = models.CharField("nome", max_length=120)
    phone = models.CharField("telefone", max_length=20)
    email = models.EmailField("e-mail", max_length=254, blank=True)
    notes = models.TextField(
        "observações",
        blank=True,
        help_text="Anotações internas do salão (texto simples, sem HTML).",
    )
    birthday = models.DateField("aniversário", null=True, blank=True)
    lgpd_consent = models.BooleanField("consentimento LGPD", default=False)
    lgpd_consent_at = models.DateTimeField(
        "consentimento em",
        null=True,
        blank=True,
        help_text="Carimbo da última concessão de consentimento (apagado se revogado).",
    )

    class Meta:
        verbose_name = "cliente"
        verbose_name_plural = "clientes"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.phone})"
