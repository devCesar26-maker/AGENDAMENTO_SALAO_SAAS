"""Lista de espera e estado de entrega de notificações."""

import secrets

from django.db import models
from django.utils import timezone

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


class WaitlistOffer(TenantModel):
    """Oferta exclusiva e temporária de um item liberado para o primeiro da fila."""

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Ativa"
        CONVERTED = "CONVERTED", "Convertida"
        EXPIRED = "EXPIRED", "Expirada"

    entry = models.ForeignKey(
        WaitlistEntry, on_delete=models.CASCADE, related_name="priority_offers"
    )
    appointment_item = models.ForeignKey(
        "scheduling.AppointmentItem", on_delete=models.CASCADE, related_name="waitlist_offers"
    )
    token = models.CharField(
        "token", max_length=64, unique=True, db_index=True, default=secrets.token_urlsafe
    )
    expires_at = models.DateTimeField("expira em", db_index=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    converted_appointment = models.ForeignKey(
        "scheduling.Appointment",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="converted_waitlist_offers",
    )

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=("appointment_item",),
                condition=models.Q(status="ACTIVE"),
                name="uniq_active_offer_per_item",
            ),
            models.UniqueConstraint(
                fields=("entry",),
                condition=models.Q(status="ACTIVE"),
                name="uniq_active_offer_per_entry",
            ),
        ]
        indexes = [models.Index(fields=["organization", "status", "expires_at"])]

    def __str__(self):
        return f"{self.entry} — {self.appointment_item}"

    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE and self.expires_at > timezone.now()


class NotificationEvent(TenantModel):
    """Outbox transacional para que indisponibilidade do broker não perca e-mails."""

    class Kind(models.TextChoices):
        CONFIRMATION = "CONFIRMATION", "Confirmação de agendamento"
        CANCELLATION = "CANCELLATION", "Cancelamento de agendamento"
        WAITLIST_OPENING = "WAITLIST_OPENING", "Vaga aberta da lista de espera"
        WAITLIST_PRIORITY = "WAITLIST_PRIORITY", "Oferta prioritária da lista de espera"
        RATING_REQUEST = "RATING_REQUEST", "Pedido de avaliação"
        RECURRING_SUGGESTION = "RECURRING_SUGGESTION", "Sugestão de recorrência"

    class State(models.TextChoices):
        PENDING = "PENDING", "Pendente"
        PROCESSING = "PROCESSING", "Em processamento"
        SENT = "SENT", "Enviado"

    appointment = models.ForeignKey(
        "scheduling.Appointment",
        on_delete=models.CASCADE,
        related_name="notification_events",
    )
    waitlist_offer = models.ForeignKey(
        WaitlistOffer,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="notification_events",
    )
    kind = models.CharField(max_length=24, choices=Kind.choices)
    state = models.CharField(max_length=12, choices=State.choices, default=State.PENDING)
    available_at = models.DateTimeField(default=timezone.now, db_index=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=500, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("appointment", "kind", "waitlist_offer"),
                name="uniq_notification_event_appointment_kind",
            )
        ]
        indexes = [models.Index(fields=("state", "available_at"), name="notification_outbox_idx")]
