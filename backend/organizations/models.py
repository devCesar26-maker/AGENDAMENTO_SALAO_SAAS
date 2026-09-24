"""Modelos de domínio: salões, memberships e convites."""

import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel


class Organization(TimeStampedModel):
    """Um salão/barbearia (tenant) na plataforma."""

    name = models.CharField("nome", max_length=120)
    slug = models.SlugField(
        "slug", max_length=60, unique=True, help_text="Usado na URL pública /b/<slug>"
    )
    timezone = models.CharField("fuso horário", max_length=64, default="America/Sao_Paulo")
    phone = models.CharField("telefone", max_length=20, blank=True)
    address = models.CharField("endereço", max_length=255, blank=True)
    working_hours = models.JSONField(
        "horário de funcionamento",
        default=dict,
        blank=True,
        help_text='Ex.: {"mon": [["09:00", "18:00"]], "sun": []}',
    )
    is_active = models.BooleanField("ativo", default=True)

    class Meta:
        verbose_name = "salão"
        verbose_name_plural = "salões"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Membership(TimeStampedModel):
    """Vínculo entre usuário e salão, com papel (role)."""

    class Role(models.TextChoices):
        OWNER = "OWNER", "Proprietário"
        MANAGER = "MANAGER", "Gerente"
        PROFESSIONAL = "PROFESSIONAL", "Profissional"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField("papel", max_length=20, choices=Role.choices, default=Role.PROFESSIONAL)

    class Meta:
        verbose_name = "membro"
        verbose_name_plural = "membros"
        constraints = [
            models.UniqueConstraint(
                fields=("user", "organization"), name="uniq_membership_user_org"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.organization} ({self.role})"


class Invitation(TimeStampedModel):
    """Convite por e-mail para ingressar em um salão, com token expirável."""

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="invitations"
    )
    email = models.EmailField("e-mail")
    role = models.CharField(
        "papel",
        max_length=20,
        choices=Membership.Role.choices,
        default=Membership.Role.PROFESSIONAL,
    )
    token = models.CharField("token", max_length=64, unique=True, editable=False)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invitations_sent",
    )
    accepted_at = models.DateTimeField("aceito em", null=True, blank=True)
    expires_at = models.DateTimeField("expira em")

    class Meta:
        verbose_name = "convite"
        verbose_name_plural = "convites"
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "email"),
                condition=models.Q(accepted_at__isnull=True),
                name="uniq_active_invitation_per_email",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=7)
        super().save(*args, **kwargs)

    @property
    def is_valid(self) -> bool:
        return self.accepted_at is None and timezone.now() < self.expires_at
