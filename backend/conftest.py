"""Fixtures compartilhadas de testes (pytest)."""

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from accounts.factories import UserFactory
from organizations.factories import MembershipFactory, OrganizationFactory

SENHA_PADRAO = "Senha#2026!"


@pytest.fixture(autouse=True)
def limpa_cache_entre_testes():
    """LocMemCache persiste no processo; limpa lockout/throttle a cada teste."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client() -> APIClient:
    """Cliente DRF sem autenticação."""
    return APIClient()


@pytest.fixture
def organization():
    """Salão A com um OWNER."""
    from billing.models import Plan, PlanTier, Subscription

    org = OrganizationFactory()
    Subscription.objects.filter(organization=org).update(
        plan=Plan.objects.get(tier=PlanTier.PLUS)
    )
    owner = UserFactory()
    MembershipFactory(organization=org, user=owner, role="OWNER")
    org._owner = owner
    return org


@pytest.fixture
def auth_client(api_client, organization) -> APIClient:
    """Client autenticado como OWNER do salão A."""
    api_client.force_authenticate(user=organization._owner)
    return api_client


# ── Fixtures de roles para a Fase 2 (catálogo e clientes) ─────────────────


@pytest.fixture
def manager(organization):
    """Usuário MANAGER do salão A."""
    user = UserFactory()
    MembershipFactory(organization=organization, user=user, role="MANAGER")
    return user


@pytest.fixture
def manager_client(api_client, organization, manager) -> APIClient:
    api_client.force_authenticate(user=manager)
    return api_client


@pytest.fixture
def professional_user(organization):
    """Usuário com membership PROFESSIONAL no salão A (sem perfil vinculado)."""
    user = UserFactory()
    MembershipFactory(organization=organization, user=user, role="PROFESSIONAL")
    return user


@pytest.fixture
def professional_client(api_client, professional_user) -> APIClient:
    api_client.force_authenticate(user=professional_user)
    return api_client


@pytest.fixture
def professional(organization, professional_user):
    """Perfil de profissional do salão A vinculado ao PROFESSIONAL."""
    from catalog.factories import ProfessionalFactory

    return ProfessionalFactory(organization=organization, user=professional_user)


@pytest.fixture
def other_organization():
    """Salão B (isolation tenant) com OWNER, PROFESSIONAL e perfil vinculado."""
    from catalog.factories import ProfessionalFactory

    org = OrganizationFactory()
    owner = UserFactory()
    MembershipFactory(organization=org, user=owner, role="OWNER")
    professional_user = UserFactory()
    MembershipFactory(organization=org, user=professional_user, role="PROFESSIONAL")
    org._owner = owner
    org._professional = ProfessionalFactory(
        organization=org, user=professional_user, name="Pro do salão B"
    )
    return org
