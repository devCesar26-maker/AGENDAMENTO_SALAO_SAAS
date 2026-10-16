"""Factory de clientes (customers) para testes."""

from factory import Sequence, SubFactory
from factory.django import DjangoModelFactory

from organizations.factories import OrganizationFactory

from .models import Customer


class CustomerFactory(DjangoModelFactory):
    class Meta:
        model = Customer

    organization = SubFactory(OrganizationFactory)
    name = Sequence(lambda n: f"Cliente {n}")
    phone = Sequence(lambda n: f"+551191010{1000 + n}")
    email = ""
    notes = ""
