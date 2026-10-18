"""Regras de negócio do catálogo (views ficam finas)."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework.exceptions import ValidationError as DRFValidationError

from catalog.models import Professional, ProfessionalService, Service


@transaction.atomic
def create_professional(*, organization, validated_data):
    """Cria profissional respeitando atomicamente o limite do plano."""
    from billing.services import check_professional_limit

    check_professional_limit(organization)
    return Professional.objects.create(organization=organization, **validated_data)


def link_service_to_professional(
    *,
    professional: Professional,
    service: Service,
    price_override=None,
    duration_override=None,
    commission_percentage=None,
) -> ProfessionalService:
    """
    Vincula um serviço a um profissional com overrides opcionais. O serviço
    TEM de pertencer ao mesmo salão do profissional (defesa adicional: além da
    validação do serializer, o service também confere — é chamado em qualquer
    contexto, incluindo Celery).
    """
    if service.organization_id != professional.organization_id:
        raise DRFValidationError({"service": ["Serviço não pertence a este salão."]})
    link = ProfessionalService(
        professional=professional,
        service=service,
        organization=professional.organization,
        price_override=price_override,
        duration_override=duration_override,
        commission_percentage=(
            Decimal("0.00") if commission_percentage is None else commission_percentage
        ),
    )
    try:
        link.full_clean()  # validadores de campo + unique (professional, service)
        link.save()
    except ValidationError as exc:
        raise DRFValidationError(exc.message_dict) from exc
    return link


@transaction.atomic
def unlink_service_to_professional(link: ProfessionalService) -> None:
    """Desvincula (DELETE). Vazio de regra hoje; ponto de extensão futuro."""
    link.delete()
