"""
Regras de negócio de salões, membros e convites (views ficam finas).
"""

from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from core.api.exceptions import BusinessError
from organizations.models import Invitation, Membership, Organization


def _invitation_api_error(field: str | None, detail: str):
    from rest_framework.exceptions import ValidationError

    return ValidationError({field: [detail]} if field else detail)


_INVITATION_EXPIRA_DAYS = 7


def create_invitation(
    *, organization: "Organization", email: str, role: str, invited_by=None
) -> Invitation:
    """Cria convite pendente com token seguro e dispara o e-mail de convite."""
    email = email.strip().lower()
    has_pending = Invitation.objects.filter(
        organization=organization, email=email, accepted_at__isnull=True
    ).exists()
    if has_pending:
        raise _invitation_api_error(
            "email", "Este e-mail já possui um convite pendente para este salão."
        )

    invitation = Invitation.objects.create(
        organization=organization,
        email=email,
        role=role,
        invited_by=invited_by,
        expires_at=timezone.now() + timedelta(days=_INVITATION_EXPIRA_DAYS),
    )
    _send_invitation_email(invitation)
    return invitation


def revoke_invitation(invitation: Invitation) -> None:
    """Revoga um convite removendo o token pendente."""
    invitation.delete()


def _send_invitation_email(invitation: Invitation) -> None:
    invite_url = f"{settings.FRONTEND_URL.rstrip('/')}/convite/{invitation.token}"
    context = {
        "organization_name": invitation.organization.name,
        "role": invitation.get_role_display(),
        "invite_url": invite_url,
        "expires_at": timezone.localtime(invitation.expires_at),
        "inviter": (invitation.invited_by.get_full_name() if invitation.invited_by else ""),
    }
    body = render_to_string("emails/organization_invitation.txt", context)
    send_mail(
        subject=f"Convite para {invitation.organization.name} — Éclat Studio",
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[invitation.email],
    )


@transaction.atomic
def accept_invitation(
    *,
    token: str,
    password: str | None = None,
    first_name: str = "",
    last_name: str = "",
    authenticated_user=None,
) -> Membership:
    """
    Aceita um convite: cria o User se não existir (com senha informada) ou
    vincula o User existente, e cria o Membership com o role do convite.
    """
    invitation = Invitation.objects.select_related("organization").filter(token=token).first()
    if invitation is None or not invitation.is_valid:
        raise _invitation_api_error(None, "Convite inválido ou já utilizado.")

    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = User.objects.filter(email__iexact=invitation.email).first()
    if user is None:
        if not password:
            raise _invitation_api_error(
                "password",
                "Informe uma senha para criar sua conta e aceitar o convite.",
            )
        user = User.objects.create_user(
            email=invitation.email,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )
    elif authenticated_user is None or not authenticated_user.is_authenticated:
        raise _invitation_api_error(
            None, "Entre na conta associada a este e-mail para aceitar o convite."
        )
    elif authenticated_user.pk != user.pk:
        raise _invitation_api_error(
            None, "Entre na conta associada ao e-mail do convite para continuar."
        )

    if Membership.objects.filter(user=user, organization=invitation.organization).exists():
        raise _invitation_api_error(None, "Você já pertence a este salão.")

    membership = Membership.objects.create(
        user=user, organization=invitation.organization, role=invitation.role
    )
    invitation.accepted_at = timezone.now()
    invitation.save(update_fields=["accepted_at", "updated_at"])
    return membership


@transaction.atomic
def update_member(
    membership: Membership,
    *,
    role: str | None = None,
    is_active: bool | None = None,
    actor=None,
) -> Membership:
    """
    Altera role e/ou status do membro. O salão precisa manter pelo menos um
    PROPRIETÁRIO ativo — não é possível desativar/demover o último owner.
    """
    becomes_less_than_owner = role is not None and role != Membership.Role.OWNER
    is_being_deactivated = is_active is False and membership.is_active

    if actor is not None and actor.user_id == membership.user_id and role is not None:
        raise _invitation_api_error("role", "Você não pode alterar o próprio papel.")

    if membership.role == Membership.Role.OWNER and (
        is_being_deactivated or becomes_less_than_owner
    ):
        still_has_owner = (
            Membership.objects.filter(
                organization=membership.organization,
                role=Membership.Role.OWNER,
                is_active=True,
            )
            .exclude(pk=membership.pk)
            .exists()
        )
        if not still_has_owner:
            raise BusinessError(
                "O salão precisa de pelo menos um proprietário ativo.",
                code="last_owner",
            )

    was_active = membership.is_active
    if role is not None:
        membership.role = role
    if is_active is not None:
        membership.is_active = is_active
    membership.save(update_fields=["role", "is_active", "updated_at"])
    if was_active and not membership.is_active:
        from analytics.models import AuditLog
        from analytics.services import record_audit

        record_audit(
            organization=membership.organization,
            action=AuditLog.Action.MEMBER_REMOVED,
            actor=actor,
            object_type="membership",
            object_id=membership.pk,
        )
    return membership


def validar_working_hours(value) -> None:
    """
    Valida formato do horário de funcionamento:
    {"mon": [["09:00", "18:00"]], ...} (dias mon..sun; lista vazia = fechado).
    Raises ValidationError do Django.
    """
    if not isinstance(value, dict):
        raise ValidationError("Horário de funcionamento deve ser um objeto por dia da semana.")
    valid_days = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
    for day, ranges in value.items():
        if day not in valid_days:
            raise ValidationError(f"Dia inválido: {day}.")
        if not ranges:
            continue
        if not isinstance(ranges, list):
            raise ValidationError(f"Intervalo de {day} deve ser uma lista.")
        for r in ranges:
            if not (isinstance(r, (list, tuple)) and len(r) == 2):
                raise ValidationError(f'Intervalo de {day} inválido: use ["HH:MM", "HH:MM"].')
