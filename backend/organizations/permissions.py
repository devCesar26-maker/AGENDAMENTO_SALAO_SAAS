"""
Permissões de salão: role resolvível pela Membership ativa do usuário.

Views expõem `get_organization()` (resolvida pelo slug da URL); a permissão
verifica a membership ativa do usuário nesse salão. Sem membership ativa:
fail-closed.
"""

from rest_framework.permissions import BasePermission

from organizations import selectors
from organizations.models import Organization


class _BaseOrganizationRolePermission(BasePermission):
    """Base: exige membership ativa com role em `allowed_roles`."""

    allowed_roles: frozenset[str] = frozenset()

    def _has_role(self, request, organization) -> bool:
        membership = selectors.get_active_membership(request.user, organization)
        if membership is None:
            return False
        return membership.role in self.allowed_roles

    def has_permission(self, request, view) -> bool:
        organization = getattr(view, "get_organization", None)
        if organization is None:  # view não é escopada por salão
            return False
        return self._has_role(request, view.get_organization())

    def has_object_permission(self, request, view, obj) -> bool:
        # obj pode ser a própria Organization ou uma entidade com FK organization.
        organization = obj if isinstance(obj, Organization) else getattr(obj, "organization", None)
        if organization is None:
            return False
        return self._has_role(request, organization)


class IsOrganizationMember(_BaseOrganizationRolePermission):
    """Qualquer membro ativo: OWNER, MANAGER ou PROFESSIONAL."""

    message = "Você não é membro deste salão."
    allowed_roles = frozenset({"OWNER", "MANAGER", "PROFESSIONAL"})


class IsOrganizationManagerOrOwner(_BaseOrganizationRolePermission):
    """Apenas OWNER e MANAGER (editam salão, convidam, listam convites)."""

    message = "Apenas proprietários e gerentes podem executar esta ação."
    allowed_roles = frozenset({"OWNER", "MANAGER"})


class IsOrganizationOwner(_BaseOrganizationRolePermission):
    """Apenas OWNER (gerencia membros)."""

    message = "Apenas o proprietário pode executar esta ação."
    allowed_roles = frozenset({"OWNER"})
