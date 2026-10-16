"""Regras de negócio de clientes (views ficam finas)."""

from django.db import transaction
from django.utils import timezone

from customers.models import Customer


@transaction.atomic
def register_lgpd_consent(customer: Customer, *, consented: bool) -> Customer:
    """
    Registra/atualiza o consentimento LGPD do cliente. Ao consentir, grava o
    carimbo de data/hora; ao revogar, apaga o carimbo (mas preserva o histórico
    de consentimento em auditoria futura — Fase 3+).
    """
    customer.lgpd_consent = consented
    customer.lgpd_consent_at = timezone.now() if consented else None
    customer.save(update_fields=["lgpd_consent", "lgpd_consent_at", "updated_at"])
    return customer
