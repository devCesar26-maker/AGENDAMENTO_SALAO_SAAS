"""
Queries de domínio do app catalog (nenhuma regra de negócio aqui). Todas
escopadas explicitamente ao tenant; otimizadas contra N+1 para os endpoints de
listagem (`django_assert_num_queries` cobre isso nos testes).
"""

from django.db.models import Prefetch

from catalog.models import (
    Professional,
    ProfessionalService,
    Service,
    ServiceCategory,
    TimeOff,
    WorkingHours,
)


def list_service_categories(organization):
    return ServiceCategory.objects.filter(organization=organization).order_by("order", "name")


def get_service_category(organization, pk) -> ServiceCategory | None:
    return ServiceCategory.objects.filter(organization=organization, pk=pk).first()


def list_services(organization):
    return (
        Service.objects.filter(organization=organization)
        .select_related("category")
        .order_by("name")
    )


def get_service(organization, pk) -> Service | None:
    return (
        Service.objects.select_related("category").filter(organization=organization, pk=pk).first()
    )


def list_professionals(organization):
    return (
        Professional.objects.filter(organization=organization)
        .select_related("user")
        .prefetch_related(
            Prefetch(
                "service_links",
                queryset=ProfessionalService.objects.select_related("service", "service__category"),
            )
        )
        .order_by("name")
    )


def get_professional(organization, pk) -> Professional | None:
    return (
        Professional.objects.select_related("user").filter(organization=organization, pk=pk).first()
    )


def list_professional_services(professional):
    return (
        ProfessionalService.objects.filter(
            professional=professional, organization=professional.organization
        )
        .select_related("service", "service__category")
        .order_by("service__name")
    )


def get_professional_service(organization, pk) -> ProfessionalService | None:
    return (
        ProfessionalService.objects.select_related("service", "service__category", "professional")
        .filter(organization=organization, pk=pk)
        .first()
    )


def list_working_hours(professional):
    return WorkingHours.objects.filter(
        professional=professional, organization=professional.organization
    ).order_by("weekday", "start_time")


def get_working_hours(organization, pk) -> WorkingHours | None:
    return WorkingHours.objects.filter(organization=organization, pk=pk).first()


def list_time_offs(professional):
    return TimeOff.objects.filter(
        professional=professional, organization=professional.organization
    ).order_by("start_date", "end_date")


def get_time_off(organization, pk) -> TimeOff | None:
    return TimeOff.objects.filter(organization=organization, pk=pk).first()
