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
    org = OrganizationFactory()
    owner = UserFactory()
    MembershipFactory(organization=org, user=owner, role="OWNER")
    org._owner = owner
    return org


@pytest.fixture
def auth_client(api_client, organization) -> APIClient:
    """Client autenticado como OWNER do salão A."""
    api_client.force_authenticate(user=organization._owner)
    return api_client
