"""Queries de domínio do app customers (nenhuma regra de negócio aqui)."""

from django.db.models import Q

from customers.models import Customer


def list_customers(organization, *, search: str | None = None):
    """Listagem com busca opcional por nome/telefone/e-mail (pagina fica na view)."""
    qs = Customer.objects.filter(organization=organization).order_by("name")
    if search:
        qs = qs.filter(
            Q(name__icontains=search)
            | Q(phone__icontains=search)
            | Q(email__icontains=search)
        )
    return qs


def get_customer(organization, pk) -> Customer | None:
    return Customer.objects.filter(organization=organization, pk=pk).first()
