"""Lista de espera e estado de entrega de notificações."""

from django.db import models

from core.models import TenantModel


class WaitlistEntry(TenantModel):
    """Pedido de aviso quando um serviço volta a ter horário na data desejada."""

    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="waitlist_entries"
    )
    service = models.ForeignKey("catalog.Service", on_delete=models.PROTECT)
    professional = models.ForeignKey(
        "catalog.Professional", null=True, blank=True, on_delete=models.SET_NULL
    )
    desired_date = models.DateField("data desejada", db_index=True)
    notified_at = models.DateTimeField("notificado em", null=True, blank=True)
    converted_at = models.DateTimeField("convertido em", null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(
                fields=["organization", "service", "desired_date", "notified_at"],
                name="waitlist_lookup_idx",
            )
        ]

    def __str__(self):
        return f"{self.customer} — {self.service} em {self.desired_date}"
