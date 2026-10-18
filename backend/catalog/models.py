"""
Catálogo do salão: categorias, serviços, profissionais e sua configuração
(vínculos serviço-profissional, horários de trabalho e folgas).

Toda entidade herda `TenantModel` (FK `organization` + `TenantScopedManager`):
o scoping é explícito em qualquer query (`for_tenant`) e automático nas views
via `TenantModelViewSet` (core/tenant.py). O `organization_id` nas gravações
sempre vem do servidor, nunca do payload.
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import TenantModel

DURACAO_MAX_MINUTOS = 24 * 60
BUFFER_MAX_MINUTOS = 240


class ServiceCategory(TenantModel):
    """Agrupador visual do catálogo (ex.: Cortes, Coloração)."""

    name = models.CharField("nome", max_length=120)
    order = models.PositiveSmallIntegerField(
        "ordem",
        default=0,
        help_text="Ordem de exibição no catálogo (menor aparece primeiro).",
    )
    is_active = models.BooleanField("ativo", default=True)

    class Meta:
        verbose_name = "categoria de serviço"
        verbose_name_plural = "categorias de serviço"
        ordering = ["order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "name"), name="uniq_category_name_per_org"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Service(TenantModel):
    """Serviço prestado pelo salão, com duração, preço e buffer pós-atendimento."""

    category = models.ForeignKey(
        ServiceCategory,
        on_delete=models.PROTECT,
        related_name="services",
        verbose_name="categoria",
    )
    name = models.CharField("nome", max_length=120)
    description = models.CharField(
        "descrição",
        max_length=500,
        blank=True,
        help_text="Texto curto exibido na agenda/reserva (texto simples, sem HTML).",
    )
    duration_minutes = models.PositiveSmallIntegerField(
        "duração (min)",
        default=30,
        validators=[MinValueValidator(1), MaxValueValidator(DURACAO_MAX_MINUTOS)],
    )
    price = models.DecimalField(
        "preço",
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    buffer_minutes = models.PositiveSmallIntegerField(
        "buffer (min)",
        default=0,
        help_text="Tempo de limpeza/descanso após o atendimento.",
        validators=[MaxValueValidator(BUFFER_MAX_MINUTOS)],
    )
    is_active = models.BooleanField("ativo", default=True)

    class Meta:
        verbose_name = "serviço"
        verbose_name_plural = "serviços"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Professional(TenantModel):
    """
    Profissional do salão. `user` é opcional: pode existir profissional sem
    login (ex.: freelancer avulso). Quando vinculado, o usuário precisa ser
    membro ativo do mesmo salão (validado no service/serializer).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="professional_profiles",
        verbose_name="usuário",
        help_text="Conta com login vinculada; opcional.",
    )
    name = models.CharField("nome", max_length=120)
    photo = models.URLField(
        "foto",
        max_length=500,
        blank=True,
        help_text="URL pública da foto. Upload de arquivo próprio fica para fase futura.",
    )
    is_active = models.BooleanField("ativo", default=True)

    class Meta:
        verbose_name = "profissional"
        verbose_name_plural = "profissionais"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "user"),
                condition=models.Q(user__isnull=False),
                name="uniq_professional_user_per_org",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class ProfessionalService(TenantModel):
    """
    Vínculo profissional ↔ serviço, com overrides. preco_override/duracao_override
    nulos = usa os valores do serviço; comissao_percentual 0 a 100.
    """

    professional = models.ForeignKey(
        Professional, on_delete=models.CASCADE, related_name="service_links"
    )
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="service_links"
    )
    price_override = models.DecimalField(
        "preço override",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    duration_override = models.PositiveSmallIntegerField(
        "duração override (min)",
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(DURACAO_MAX_MINUTOS)],
    )
    commission_percentage = models.DecimalField(
        "comissão (%)",
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00")),
        ],
    )

    class Meta:
        verbose_name = "serviço do profissional"
        verbose_name_plural = "serviços do profissional"
        ordering = ["professional", "service"]
        constraints = [
            models.UniqueConstraint(
                fields=("professional", "service"), name="uniq_professional_service"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.professional} → {self.service}"


class WorkingHours(TenantModel):
    """
    Janela de trabalho semanal do profissional. Permite mais de uma janela no
    mesmo dia (ex.: pausa de almoço) — o motor de disponibilidade (Fase 3)
    fará a união dos intervalos.
    """

    class Weekday(models.IntegerChoices):
        SEGUNDA = 0, _("Segunda-feira")
        TERCA = 1, _("Terça-feira")
        QUARTA = 2, _("Quarta-feira")
        QUINTA = 3, _("Quinta-feira")
        SEXTA = 4, _("Sexta-feira")
        SABADO = 5, _("Sábado")
        DOMINGO = 6, _("Domingo")

    professional = models.ForeignKey(
        Professional, on_delete=models.CASCADE, related_name="working_hours"
    )
    weekday = models.SmallIntegerField(
        "dia da semana",
        choices=Weekday.choices,
        validators=[MinValueValidator(0), MaxValueValidator(6)],
        help_text="0 = segunda … 6 = domingo (ISO-8601).",
    )
    start_time = models.TimeField("início")
    end_time = models.TimeField("fim")

    class Meta:
        verbose_name = "horário de trabalho"
        verbose_name_plural = "horários de trabalho"
        ordering = ["professional", "weekday", "start_time"]

    def __str__(self) -> str:
        return f"{self.professional} · {self.get_weekday_display()} {self.start_time:%H:%M}"


class TimeOff(TenantModel):
    """Folga/bloqueio do profissional por intervalo de datas (inclusive o fim)."""

    professional = models.ForeignKey(
        Professional, on_delete=models.CASCADE, related_name="time_offs"
    )
    start_date = models.DateField("início")
    end_date = models.DateField("fim")
    reason = models.CharField("motivo", max_length=200, blank=True)

    class Meta:
        verbose_name = "folga"
        verbose_name_plural = "folgas"
        ordering = ["professional", "start_date"]

    def __str__(self) -> str:
        return f"{self.professional} · {self.start_date} a {self.end_date}"
