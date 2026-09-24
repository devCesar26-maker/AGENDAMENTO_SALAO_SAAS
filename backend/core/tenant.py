"""
Enforçamento de multi-tenancy (shared-schema).

Estratégia em duas camadas, ambas obrigatórias:

1. **ViewSet** (`TenantModelViewSet`): todo endpoint de negócio resolve o tenant
   a partir da Membership do usuário autenticado e filtra o queryset. O tenant
   NUNCA vem de parâmetro de URL/body. Falha fechada: sem membership, 403.

2. **Object-level** (`IsTenantObject` + `TenantOwnedMixin`): retrieve/update/
   destroy revalidam que o objeto pertence ao tenant (defesa em profundidade
   contra IDOR, mesmo que o queryset já tenha filtrado).

A filtragem automática via thread-local no manager foi descartada
propositalmente:Contextos fora do request/response (Celery, management commands,
admin) não têm request e a variável de thread pode "vazar" entre requisições em
servidores async — a fonte de bugs de isolamento mais comum em shared-schema.
"""

from django.core.exceptions import ImproperlyConfigured
from rest_framework.permissions import SAFE_METHODS, BasePermission

from core.models import TenantModel


def get_tenant(view) -> "organizations.Organization":  # noqa: F821
    """
    Retorna a Organization do usuário autenticado, resolvida pela Membership.

    view.org_lookup é o atributo do request onde o middleware/view base
    armazenou a organização ativa (populado por `resolve_tenant`).
    """
    org = getattr(view.request, "organization", None)
    if org is None:
        raise ImproperlyConfigured(
            "Tenant não resolvido. Use TenantModelViewSet ou chame resolve_tenant()."
        )
    return org


def resolve_tenant(request):
    """
    Resolve e cachear a organização ativa no request.

    Por simplicidade (decisão registrada no README), o usuário opera sob a
    primeira membership; suporte a múltiplos salões por usuário virá via
    header X-Organization-Id validado contra as memberships.
    """
    user = request.user
    if not user or not user.is_authenticated:
        return None
    membership = user.memberships.select_related("organization").order_by("created_at").first()
    request.organization = membership.organization if membership else None
    request.membership = membership
    return request.organization


class TenantModelViewSet:
    """
    Mixin para ViewSets de entidades TenantModel.

    - filtra o queryset pelo tenant resolvido do request;
    - injeta `organization` no save (sem aceitar do payload — anti mass assignment).
    """

    def get_queryset(self):
        qs = super().get_queryset()
        if not issubclass(qs.model, TenantModel):
            raise ImproperlyConfigured(
                f"{qs.model} não é TenantModel; não pode usar TenantModelViewSet."
            )
        org = getattr(self.request, "organization", None)
        if org is None:
            resolve_tenant(self.request)
            org = getattr(self.request, "organization", None)
        if org is None:
            # Fail-closed: sem membership => nenhuma linha visível.
            return qs.none()
        return qs.filter(organization=org)

    def perform_create(self, serializer):
        org = getattr(self.request, "organization", None) or resolve_tenant(self.request)
        serializer.save(organization=org)


class IsTenantMember(BasePermission):
    """Permite acesso apenas a usuários com Membership em algum salão."""

    message = "Usuário sem vínculo com um salão."

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        org = getattr(request, "organization", None) or resolve_tenant(request)
        return org is not None


class IsTenantObject(BasePermission):
    """
    Object-level: o objeto precisa pertencer ao tenant do request.

    Em leitura aceita qualquer membro; em escrita, restringe por role via
    `role_required` do view (validado em Phase 1 com RolePermission).
    """

    message = "Objeto pertence a outro salão."

    def has_object_permission(self, request, view, obj) -> bool:
        org = getattr(request, "organization", None) or resolve_tenant(request)
        if org is None:
            return False
        if not isinstance(obj, TenantModel):
            return False
        # Leitura: membro do tenant. Escrita: idem (roles tratadas no view).
        obj_org_id = obj.organization_id
        if request.method in SAFE_METHODS:
            return obj_org_id == org.id
        return obj_org_id == org.id
