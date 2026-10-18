"""Agendamentos e snapshots dos serviços que compõem cada atendimento."""

from django.db import models

from core.models import TenantModel


class Appointment(TenantModel):
    class Status(models.TextChoices):
        SCHEDULED = "SCHEDULED", "Agendado"
        CONFIRMED = "CONFIRMED", "Confirmado"
        COMPLETED = "COMPLETED", "Concluído"
        CANCELED = "CANCELED", "Cancelado"
        NO_SHOW = "NO_SHOW", "Não compareceu"

    class Origin(models.TextChoices):
        DASHBOARD = "DASHBOARD", "Dashboard"
        PUBLIC_PAGE = "PUBLIC_PAGE", "Página pública"

    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.PROTECT, related_name="appointments"
    )
    status = models.CharField(
        "status",
        max_length=20,
        choices=Status.choices,
        default=Status.SCHEDULED,
        db_index=True,
    )
    origin = models.CharField(
        "origem", max_length=20, choices=Origin.choices, default=Origin.DASHBOARD
    )
    created_by = models.ForeignKey(
        "organizations.Membership",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="appointments_created",
    )
    notes = models.TextField("observações", blank=True)
    reminder_sent_at = models.DateTimeField(
        "lembrete enviado em", null=True, blank=True
    )

    class Meta:
        ordering = ["-created_at"]


class AppointmentItem(TenantModel):
    appointment = models.ForeignKey(
        Appointment, on_delete=models.CASCADE, related_name="items"
    )
    service = models.ForeignKey("catalog.Service", on_delete=models.PROTECT)
    professional = models.ForeignKey("catalog.Professional", on_delete=models.PROTECT)
    order = models.PositiveSmallIntegerField("ordem")
    start_at = models.DateTimeField("início", db_index=True)
    end_at = models.DateTimeField("fim")
    buffer_minutes = models.PositiveSmallIntegerField(
        "buffer no agendamento", default=0
    )
    price = models.DecimalField("preço no agendamento", max_digits=10, decimal_places=2)
    commission_percentage = models.DecimalField(
        "comissão no agendamento", max_digits=5, decimal_places=2, default=0
    )

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["appointment", "order"], name="uniq_appointment_item_order"
            )
        ]
        indexes = [models.Index(fields=["professional", "start_at", "end_at"])]
