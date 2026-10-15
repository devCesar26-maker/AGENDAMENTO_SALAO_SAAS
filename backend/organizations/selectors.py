"""
Queries de domínio do app organizations (nenhuma regra de negócio aqui).
"""

from django.utils import timezone

from organizations.models import Invitation, Membership, Organization


def get_organization_by_slug(slug: str) -> Organization | None:
    """Busca um salão pelo slug; None quando não existe (views traduzem para 404)."""
    return Organization.objects.filter(slug=slug).first()


def get_active_membership(user, organization: Organization) -> Membership | None:
    """Membership ativa do usuário no salão (None se não for membro)."""
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    return (
        Membership.objects.filter(is_active=True)
        .select_related("organization")
        .filter(user=user, organization=organization)
        .first()
    )


def list_members(organization: Organization):
    """Membros do salão com dados do usuário em uma única query (sem N+1)."""
    return (
        Membership.objects.select_related("user", "organization")
        .filter(organization=organization)
        .order_by("created_at")
    )


def list_pending_invitations(organization: Organization):
    """Convites pendentes e não expirados do salão."""
    return (
        Invitation.objects.select_related("organization", "invited_by")
        .filter(organization=organization, accepted_at__isnull=True, expires_at__gt=timezone.now())
        .order_by("-created_at")
    )
