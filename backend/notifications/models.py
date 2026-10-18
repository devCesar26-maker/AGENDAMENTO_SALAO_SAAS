"""Lista de espera e estado de entrega de notificações."""

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


class NotificationEvent(TenantModel):
    """Outbox transacional para que indisponibilidade do broker não perca e-mails."""

    class Kind(models.TextChoices):
        CONFIRMATION = "CONFIRMATION", "Confirmação de agendamento"
        CANCELLATION = "CANCELLATION", "Cancelamento de agendamento"
        WAITLIST_OPENING = "WAITLIST_OPENING", "Vaga aberta da lista de espera"

    class State(models.TextChoices):
        PENDING = "PENDING", "Pendente"
        PROCESSING = "PROCESSING", "Em processamento"
        SENT = "SENT", "Enviado"

    appointment = models.ForeignKey(
        "scheduling.Appointment",
        on_delete=models.CASCADE,
        related_name="notification_events",
    )
    kind = models.CharField(max_length=24, choices=Kind.choices)
    state = models.CharField(
        max_length=12, choices=State.choices, default=State.PENDING
    )
    available_at = models.DateTimeField(default=timezone.now, db_index=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=500, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("appointment", "kind"),
                name="uniq_notification_event_appointment_kind",
            )
        ]
        indexes = [
            models.Index(
                fields=("state", "available_at"), name="notification_outbox_idx"
            )
        ]
