"""Regras de negócio de clientes (views ficam finas)."""

import hashlib

from django.db import connection, transaction
from django.utils import timezone

from customers.models import Customer


def lock_customer_identity(organization, *, phone: str, email: str = "") -> None:
    """Serializa gravações públicas da mesma identidade sem travar o tenant todo."""
    identities = [f"phone:{phone}"]
    if email:
        identities.append(f"email:{email.strip().lower()}")
    if connection.vendor == "postgresql":
        lock_ids = sorted(
            int.from_bytes(
                hashlib.blake2b(f"{organization.pk}:{identity}".encode(), digest_size=8).digest(),
                byteorder="big",
                signed=True,
            )
            for identity in identities
        )
        with connection.cursor() as cursor:
            for lock_id in lock_ids:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_id])
        return

    # Fallback para bancos sem advisory lock; produção é PostgreSQL.
    from organizations.models import Organization

    Organization.objects.select_for_update().get(pk=organization.pk)


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
