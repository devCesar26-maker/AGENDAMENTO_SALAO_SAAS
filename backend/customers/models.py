"""
Clientes do salão (CRM simples) — dados pessoais com consentimento LGPD.

Inclui o cliente no padrão de tenant: herda `TenantModel` e é escopada
explicitamente (`for_tenant`) em selectors/views; o `organization_id` nunca
vem do payload.
"""

from django.core.exceptions import ValidationError
from django.db import models

from core.models import TenantModel


class Customer(TenantModel):
    """Cliente/atendido; contatos podem vir do responsável cadastrado."""

    name = models.CharField("nome", max_length=120)
    phone = models.CharField("telefone", max_length=20, blank=True)
    email = models.EmailField("e-mail", max_length=254, blank=True)
    responsavel = models.ForeignKey(
        "self",
        verbose_name="responsável",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="dependentes",
        help_text="Contato usado para notificações. Responsáveis não podem ser dependentes.",
    )
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

    def clean(self):
        super().clean()
        if not self.responsavel_id and not self.phone.strip():
            raise ValidationError({"phone": "Informe um telefone para clientes sem responsável."})
        if self.responsavel_id == self.pk and self.pk:
            raise ValidationError(
                {"responsavel": "Um cliente não pode ser responsável de si mesmo."}
            )
        if self.responsavel_id and self.responsavel.responsavel_id:
            raise ValidationError({"responsavel": "Não são permitidas cadeias de responsáveis."})
        if self.responsavel_id and self.organization_id != self.responsavel.organization_id:
            raise ValidationError(
                {"responsavel": "O responsável deve pertencer à mesma organização."}
            )
        if self.responsavel_id and self.pk and self.dependentes.exists():
            raise ValidationError(
                {"responsavel": "Um responsável com dependentes não pode ser dependente."}
            )

    @property
    def notification_contact(self):
        return self.responsavel or self
