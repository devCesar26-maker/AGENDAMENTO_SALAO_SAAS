"""Agendamentos e snapshots dos serviços que compõem cada atendimento."""

import secrets
from datetime import timedelta
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from core.models import TenantModel


class Appointment(TenantModel):
    class Status(models.TextChoices):
        SCHEDULED = "SCHEDULED", "Agendado"
        CONFIRMED = "CONFIRMED", "Confirmado"
        COMPLETED = "COMPLETED", "Concluído"
        CANCELED = "CANCELED", "Cancelado"
        NO_SHOW = "NO_SHOW", "Não compareceu"
        SUGGESTED = "SUGGESTED", "Sugerido"

    class Origin(models.TextChoices):
        DASHBOARD = "DASHBOARD", "Dashboard"
        PUBLIC_PAGE = "PUBLIC_PAGE", "Página pública"
        RECURRING = "RECURRING", "Sugestão de recorrência"

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
    reminder_sent_at = models.DateTimeField("lembrete enviado em", null=True, blank=True)
    suggestion_expires_at = models.DateTimeField("sugestão expira em", null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class AppointmentItem(TenantModel):
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name="items")
    service = models.ForeignKey("catalog.Service", on_delete=models.PROTECT)
    professional = models.ForeignKey("catalog.Professional", on_delete=models.PROTECT)
    order = models.PositiveSmallIntegerField("ordem")
    start_at = models.DateTimeField("início", db_index=True)
    end_at = models.DateTimeField("fim")
    buffer_minutes = models.PositiveSmallIntegerField("buffer no agendamento", default=0)
    price = models.DecimalField("preço no agendamento", max_digits=10, decimal_places=2)
    commission_percentage = models.DecimalField(
        "comissão no agendamento", max_digits=5, decimal_places=2, default=0
    )
    discount_percent = models.PositiveSmallIntegerField("desconto aplicado (%)", default=0)
    flash_slot = models.ForeignKey(
        "scheduling.FlashSlot",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="appointment_items",
    )

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["appointment", "order"], name="uniq_appointment_item_order"
            )
        ]
        indexes = [models.Index(fields=["professional", "start_at", "end_at"])]


class AppointmentToken(TenantModel):
    """Token seguro para acesso público a um agendamento específico (link mágico)."""

    class Action(models.TextChoices):
        VIEW = "VIEW", "Visualizar"
        CANCEL = "CANCEL", "Cancelar"
        RATE = "RATE", "Avaliar"
        CONFIRM = "CONFIRM", "Confirmar sugestão"

    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name="tokens")
    token = models.CharField(
        "token", max_length=64, unique=True, db_index=True, default=secrets.token_urlsafe
    )
    action = models.CharField("ação", max_length=10, choices=Action.choices, default=Action.VIEW)
    expires_at = models.DateTimeField("expira em")
    used_at = models.DateTimeField("usado em", null=True, blank=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=7)
        super().save(*args, **kwargs)

    def is_valid(self):
        statuses = {
            self.Action.RATE: [Appointment.Status.COMPLETED],
            self.Action.CONFIRM: [Appointment.Status.SUGGESTED],
        }.get(
            self.action,
            [Appointment.Status.SCHEDULED, Appointment.Status.CONFIRMED],
        )
        return (
            self.used_at is None
            and self.expires_at > timezone.now()
            and self.appointment.status in statuses
        )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["token", "expires_at"]),
            models.Index(fields=["appointment", "expires_at"]),
        ]


class Rating(TenantModel):
    """Avaliação única do cliente para um atendimento concluído."""

    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name="rating")
    score = models.PositiveSmallIntegerField(
        "nota", validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField("comentário", blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(score__gte=1, score__lte=5),
                name="rating_score_between_1_and_5",
            )
        ]

    def __str__(self) -> str:
        return f"{self.appointment_id}: {self.score}/5"


class FlashSlot(TenantModel):
    """Horário promocional com desconto limitado e expiração própria."""

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Ativo"
        BOOKED = "BOOKED", "Reservado"
        EXPIRED = "EXPIRED", "Expirado"

    service = models.ForeignKey("catalog.Service", on_delete=models.CASCADE)
    professional = models.ForeignKey("catalog.Professional", on_delete=models.CASCADE)
    start_at = models.DateTimeField("início", db_index=True)
    end_at = models.DateTimeField("fim")
    original_price = models.DecimalField("preço original", max_digits=10, decimal_places=2)
    discount_percent = models.PositiveSmallIntegerField("desconto (%)")
    discount_price = models.DecimalField("preço com desconto", max_digits=10, decimal_places=2)
    expires_at = models.DateTimeField("expira em", db_index=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ["start_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(discount_percent__gte=0, discount_percent__lte=100),
                name="flash_discount_between_0_and_100",
            ),
            models.UniqueConstraint(
                fields=("organization", "service", "professional", "start_at"),
                condition=models.Q(status="ACTIVE"),
                name="uniq_active_flash_slot",
            ),
        ]
        indexes = [models.Index(fields=["organization", "status", "expires_at"])]

    def __str__(self) -> str:
        return f"{self.service} · {self.start_at:%d/%m %H:%M} · -{self.discount_percent}%"

    def save(self, *args, **kwargs):
        if self.original_price is not None and self.discount_percent is not None:
            multiplier = Decimal(100 - self.discount_percent) / Decimal(100)
            self.discount_price = (self.original_price * multiplier).quantize(Decimal("0.01"))
        super().save(*args, **kwargs)
