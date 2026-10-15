"""Factories de salões, memberships e convites (organizations)."""

from factory import Faker, PostGenerationMethodCall, Sequence, SubFactory
from factory.django import DjangoModelFactory

from accounts.factories import UserFactory


class OrganizationFactory(DjangoModelFactory):
    """Salão com slug gerado automaticamente no save()."""

    class Meta:
        model = "organizations.Organization"

    name = Sequence(lambda n: f"Salão Bello Nº{n}")
    timezone = "America/Sao_Paulo"
    phone = "+55 11 95555-0000"
    address = "Rua das Flores, 100 — São Paulo/SP"
    working_hours = {"mon": [["09:00", "18:00"]], "sun": []}


class MembershipFactory(DjangoModelFactory):
    class Meta:
        model = "organizations.Membership"

    organization = SubFactory(OrganizationFactory)
    user = SubFactory(UserFactory)
    role = "OWNER"


class InvitationFactory(DjangoModelFactory):
    class Meta:
        model = "organizations.Invitation"

    organization = SubFactory(OrganizationFactory)
    email = Sequence(lambda n: f"convidado{n}@exemplo.com.br")
    role = "PROFESSIONAL"
