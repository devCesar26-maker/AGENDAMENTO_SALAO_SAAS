"""Permissões por role e vínculo aos itens do agendamento."""

from rest_framework.permissions import BasePermission

from core.tenant import resolve_membership
from organizations.models import Membership


class AppointmentAccess(BasePermission):
    message = "Profissionais só podem acessar agendamentos que incluem seu perfil."

    def has_permission(self, request, view):
        _, membership = resolve_membership(request)
        return membership is not None

    def has_object_permission(self, request, view, obj):
        organization, membership = resolve_membership(request)
        if (
            organization is None
            or membership is None
            or obj.organization_id != organization.id
        ):
            return False
        if membership.role in (Membership.Role.OWNER, Membership.Role.MANAGER):
            return True
        if membership.role == Membership.Role.PROFESSIONAL:
            return obj.items.filter(professional__user_id=request.user.pk).exists()
        return False


class AppointmentCreateAccess(BasePermission):
    """Qualquer membro pode criar no dashboard; o escopo do pro é validado na view."""

    def has_permission(self, request, view):
        _, membership = resolve_membership(request)
        return membership is not None
