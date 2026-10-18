"""
Modelos de domínio: salões, memberships e convites.
"""

import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from core.models import TenantScopedManager, TimeStampedModel


class Organization(TimeStampedModel):
    """Um salão/barbearia (tenant) na plataforma."""

    class Vertical(models.TextChoices):
        SALAO = "SALAO", "Salão"
        BARBEARIA = "BARBEARIA", "Barbearia"

    name = models.CharField("nome", max_length=120)
    vertical = models.CharField(
        "vertical", max_length=20, choices=Vertical.choices, default=Vertical.SALAO
    )
    tema_cor = models.CharField("tema de cor", max_length=7, default="#8B5CF6")
    slug = models.SlugField(
        "slug",
        max_length=60,
        unique=True,
        blank=True,
        help_text=(
            "Gerado automaticamente a partir do nome se omitido; "
            "pode ser editado depois. Usado nas URLs."
        ),
    )
    timezone = models.CharField(
        "fuso horário", max_length=64, default="America/Sao_Paulo"
    )
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

    def save(self, *args, **kwargs):
        """Gera slug único a partir do nome quando omitido (editável depois)."""
        if not self.slug:
            base = slugify(self.name)[:54] or "salao"
            candidate, i = base, 2
            while (
                type(self).objects.exclude(pk=self.pk).filter(slug=candidate).exists()
            ):
                candidate = f"{base[:55]}-{i}"
                i += 1
            self.slug = candidate
        super().save(*args, **kwargs)


class Membership(TimeStampedModel):
    """Vínculo entre usuário e salão, com papel (role) e status ativo."""

    class Role(models.TextChoices):
        OWNER = "OWNER", "Proprietário"
        MANAGER = "MANAGER", "Gerente"
        PROFESSIONAL = "PROFESSIONAL", "Profissional"

    objects = TenantScopedManager()

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(
        "papel", max_length=20, choices=Role.choices, default=Role.PROFESSIONAL
    )
    is_active = models.BooleanField(
        "ativo",
        default=True,
        help_text="Desativado = sem acesso ao salão (não aparece na agenda).",
    )

    class Meta:
        verbose_name = "membro"
        verbose_name_plural = "membros"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=("user", "organization"), name="uniq_membership_user_org"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.organization} ({self.role})"


class Invitation(TimeStampedModel):
    """Convite por e-mail para ingressar em um salão, com token expirável."""

    objects = TenantScopedManager()

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
        ordering = ["-created_at"]
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
