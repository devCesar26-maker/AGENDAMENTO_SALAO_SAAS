"""Testes do manager tenant-scoped genérico (core.models)."""

import pytest

from accounts.factories import UserFactory
from organizations.factories import MembershipFactory, OrganizationFactory
from organizations.models import Membership


@pytest.mark.django_db
class TestTenantScopedQuerySet:
    def test_for_tenant_filtra_apenas_o_tenant_informado(self):
        org_a = OrganizationFactory()
        org_b = OrganizationFactory()
        MembershipFactory(organization=org_a)
        MembershipFactory(organization=org_a)
        MembershipFactory(organization=org_b)

        result = Membership.objects.for_tenant(org_a)

        assert result.count() == 2
        assert set(result.values_list("organization_id", flat=True)) == {org_a.id}

    def test_for_user_somente_orgs_com_membresia_ativa(self):
        user = UserFactory()
        org_ativa = OrganizationFactory()
        org_inativa = OrganizationFactory()
        MembershipFactory(organization=org_ativa, user=user, is_active=True)
        MembershipFactory(organization=org_inativa, user=user, is_active=False)

        result = Membership.objects.for_user(user)

        assert org_ativa.id in set(result.values_list("organization_id", flat=True))
        assert org_inativa.id not in set(result.values_list("organization_id", flat=True))

    def test_for_user_sem_membresia_retorna_vazio(self):
        user = UserFactory()
        assert Membership.objects.for_user(user).count() == 0
