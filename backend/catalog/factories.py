"""Factories do catálogo (catalog) para testes."""

from datetime import time

from factory import Sequence, SubFactory
from factory.django import DjangoModelFactory
from factory.fuzzy import FuzzyChoice, FuzzyDecimal, FuzzyInteger

from accounts.factories import UserFactory
from organizations.factories import OrganizationFactory

from .models import (
    Professional,
    ProfessionalService,
    Service,
    ServiceCategory,
    TimeOff,
    WorkingHours,
)


class ServiceCategoryFactory(DjangoModelFactory):
    class Meta:
        model = ServiceCategory

    organization = SubFactory(OrganizationFactory)
    name = Sequence(lambda n: f"Categoria {n}")
    order = 0


class ServiceFactory(DjangoModelFactory):
    class Meta:
        model = Service

    organization = SubFactory(OrganizationFactory)
    category = SubFactory(ServiceCategoryFactory)
    name = Sequence(lambda n: f"Serviço {n}")
    description = ""
    duration_minutes = FuzzyInteger(15, 120, step=15)
    price = FuzzyDecimal(20.0, 400.0)


class ProfessionalFactory(DjangoModelFactory):
    class Meta:
        model = Professional

    organization = SubFactory(OrganizationFactory)
    user = None  # profissional sem login por padrão; passe `user=` quando precisar
    name = Sequence(lambda n: f"Profissional {n}")
    photo = ""


class ProfessionalWithUserFactory(ProfessionalFactory):
    """Atalho para o cenário comum: profissional com conta (membro do salão)."""

    user = SubFactory(UserFactory)


class ProfessionalServiceFactory(DjangoModelFactory):
    class Meta:
        model = ProfessionalService

    organization = SubFactory(OrganizationFactory)
    professional = SubFactory(ProfessionalFactory)
    service = SubFactory(ServiceFactory)
    price_override = None
    duration_override = None
    commission_percentage = 0


class WorkingHoursFactory(DjangoModelFactory):
    class Meta:
        model = WorkingHours

    organization = SubFactory(OrganizationFactory)
    professional = SubFactory(ProfessionalFactory)
    weekday = FuzzyChoice(WorkingHours.Weekday.values)
    start_time = time(9, 0)
    end_time = time(18, 0)


class TimeOffFactory(DjangoModelFactory):
    class Meta:
        model = TimeOff

    organization = SubFactory(OrganizationFactory)
    professional = SubFactory(ProfessionalFactory)
    start_date = "2026-12-24"
    end_date = "2026-12-25"
    reason = ""
