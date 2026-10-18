"""Catálogo inicial editável criado junto com a organização."""

from catalog.models import Service, ServiceCategory
from organizations.models import Organization

VERTICAL_CATALOG = {
    Organization.Vertical.BARBEARIA: {
        "Corte Masculino": [
            ("Corte Masculino", 40, "45.00"),
            ("Corte Infantil", 30, "35.00"),
        ],
        "Barba": [("Barba", 30, "30.00")],
        "Sobrancelha": [("Sobrancelha", 15, "15.00")],
        "Combos": [("Combo Corte + Barba", 60, "65.00")],
    },
    Organization.Vertical.SALAO: {
        "Corte Feminino": [("Corte Feminino", 60, "80.00")],
        "Coloração": [("Coloração", 120, "180.00")],
        "Escova": [("Escova", 45, "55.00")],
        "Manicure": [("Manicure", 45, "40.00")],
        "Hidratação": [("Hidratação", 60, "90.00")],
    },
}


def seed_catalog(organization: Organization) -> None:
    """Insere categorias e serviços iniciais, sem lógica específica de operação."""
    for order, (category_name, services) in enumerate(
        VERTICAL_CATALOG[organization.vertical].items()
    ):
        category = ServiceCategory.objects.create(
            organization=organization, name=category_name, order=order
        )
        Service.objects.bulk_create(
            [
                Service(
                    organization=organization,
                    category=category,
                    name=name,
                    duration_minutes=duration,
                    price=price,
                )
                for name, duration, price in services
            ]
        )
