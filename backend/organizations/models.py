"""
Modelos de domínio: salões, memberships e convites.
"""

import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from core.models import TenantModel, TenantScopedManager, TimeStampedModel


def default_platform_fee_percent():
    return getattr(settings, "PLATFORM_FEE_DEFAULT_PERCENT", 10)


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
    waitlist_priority_window_minutes = models.PositiveSmallIntegerField(
        "janela de prioridade da lista de espera (min)",
        default=10,
        help_text="Tempo exclusivo para o primeiro cliente da fila reservar a vaga liberada.",
    )
    flash_slot_max_discount_percent = models.PositiveSmallIntegerField(
        "desconto máximo do FlashSlot (%)",
        default=30,
        help_text="Teto percentual aplicado aos degraus de desconto do FlashSlot.",
    )
    platform_fee_percent = models.PositiveSmallIntegerField(
        "comissão da plataforma (%)",
        default=default_platform_fee_percent,
        help_text=(
            "Percentual retido pela plataforma nas assinaturas cobradas via split "
            "do Mercado Pago. O restante é repassado ao salão."
        ),
    )
    mercadopago_seller_id = models.CharField(
        "id do vendedor no Mercado Pago",
        max_length=64,
        blank=True,
        default="",
        help_text="user_id da conta Mercado Pago conectada pelo salão (OAuth).",
    )
    mercadopago_access_token = models.CharField(
        "access token do vendedor",
        max_length=255,
        blank=True,
        default="",
        help_text="Token OAuth da conta do salão; nunca retornado pela API.",
    )
    mercadopago_refresh_token = models.CharField(
        "refresh token do vendedor",
        max_length=255,
        blank=True,
        default="",
        help_text="Refresh token OAuth da conta do salão; nunca retornado pela API.",
    )
    mercadopago_token_expires_at = models.DateTimeField(
        "expiração do token do vendedor", null=True, blank=True
    )
    mercadopago_connected_at = models.DateTimeField(
        "conta Mercado Pago conectada em", null=True, blank=True
    )

    @property
    def has_mercadopago_seller(self) -> bool:
        """True quando o salão já conectou a própria conta Mercado Pago (split ativo)."""
        return bool(self.mercadopago_seller_id and self.mercadopago_access_token)

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
            while type(self).objects.exclude(pk=self.pk).filter(slug=candidate).exists():
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
    role = models.CharField("papel", max_length=20, choices=Role.choices, default=Role.PROFESSIONAL)
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


class WebhookConfig(TenantModel):
    """Endpoint de saída (HTTPS) de um salão, com eventos assinados e segredo HMAC."""

    objects = TenantScopedManager()

    class Event(models.TextChoices):
        APPOINTMENT_CREATED = "appointment.created", "Agendamento criado"
        APPOINTMENT_COMPLETED = "appointment.completed", "Agendamento concluído"
        APPOINTMENT_CANCELED = "appointment.canceled", "Agendamento cancelado"

    url = models.URLField("endpoint", max_length=500, help_text="Deve usar HTTPS.")
    events = models.JSONField(
        "eventos assinados",
        default=list,
        help_text="Lista de eventos; use apenas valores válidos de Event.",
    )
    secret = models.CharField(
        "segredo",
        max_length=64,
        unique=True,
        editable=False,
        help_text="HMAC-SHA256 do payload. Gerado automaticamente; nunca é retornado depois da resposta de criação.",
    )
    is_active = models.BooleanField("ativo", default=True)
    last_failure_at = models.DateTimeField(
        "última falha em", null=True, blank=True, help_text="Data da última entrega que falhou."
    )
    last_failure_detail = models.CharField(
        "detalhe da última falha", max_length=500, blank=True, default=""
    )

    class Meta:
        verbose_name = "configuração de webhook"
        verbose_name_plural = "configurações de webhook"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "url"),
                name="uniq_webhook_url_per_organization",
            )
        ]

    def __str__(self) -> str:
        return f"{self.organization_id} → {self.url}"

    def save(self, *args, **kwargs):
        if not self.secret:
            self.secret = secrets.token_hex(32)
        super().save(*args, **kwargs)
