"""
Permissões do catálogo reutilizando a infraestrutura da Fase 1.

Regra nova desta fase: PROFESSIONAL edita apenas registros do PRÓPRIO perfil
(Professional, WorkingHours, TimeOff, ProfessionalService) — nunca os de outro
profissional do mesmo salão. Falha fechada: role desconhecido → negado.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from catalog.models import Professional
from core.tenant import resolve_membership
from organizations.models import Membership


class _MemberBase(BasePermission):
    """Base: membership ativa no request (qualquer role)."""

    def has_permission(self, request, view) -> bool:
        if not request.user.is_authenticated:
            return False
        _, membership = resolve_membership(request)
        return membership is not None


class NestedProfessionalAccess(_MemberBase):
    """
    Rotas aninhadas `/professionals/{id}/...`:
    - leitura: qualquer membro do salão;
    - escrita: OWNER/MANAGER em qualquer profissional; PROFESSIONAL apenas no
      próprio perfil.
    """

    message = "Profissionais só podem gerenciar os próprios registros."

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        if request.method in SAFE_METHODS:
            return True
        professional = view.get_professional()  # 404 se não for do tenant
        _, membership = resolve_membership(request)
        if membership.role == Membership.Role.PROFESSIONAL:
            return professional.user_id == request.user.id
        return membership.role in (Membership.Role.OWNER, Membership.Role.MANAGER)


class ProfessionalObjectPermission(_MemberBase):
    """
    Object-level para registros de profissional (detail routes):
    - leitura: qualquer membro do salão (a agenda precisa consultar todos);
    - escrita: OWNER/MANAGER em qualquer um; PROFESSIONAL apenas o próprio.
    """

    message = "Profissionais só podem editar os próprios registros."

    def has_object_permission(self, request, view, obj) -> bool:
        organization, membership = resolve_membership(request)
        if membership is None or organization is None:
            return False
        # Defesa em profundidade contra IDOR (o queryset já filtra o tenant):
        if getattr(obj, "organization_id", None) != organization.id:
            return False
        if request.method in SAFE_METHODS:
            return True
        if membership.role in (Membership.Role.OWNER, Membership.Role.MANAGER):
            return True
        if membership.role == Membership.Role.PROFESSIONAL:
            professional = (
                obj
                if isinstance(obj, Professional)
                else getattr(obj, "professional", None)
            )
            return professional is not None and professional.user_id == request.user.id
        return False
