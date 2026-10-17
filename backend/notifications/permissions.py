"""Permissões da lista de espera por tenant e papel."""

from rest_framework.permissions import BasePermission

from core.tenant import resolve_membership
from organizations.models import Membership


class WaitlistManagerAccess(BasePermission):
    message = "Somente OWNER e MANAGER podem administrar a lista de espera."

    def has_permission(self, request, view):
        organization, membership = resolve_membership(request)
        return bool(
            organization
            and membership
            and membership.role in (Membership.Role.OWNER, Membership.Role.MANAGER)
        )

    def has_object_permission(self, request, view, obj):
        organization, membership = resolve_membership(request)
        return bool(
            organization
            and membership
            and obj.organization_id == organization.id
            and membership.role in (Membership.Role.OWNER, Membership.Role.MANAGER)
        )
