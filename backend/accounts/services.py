"""
Regras de negócio de autenticação: registro, login com bloqueio temporário,
logout e recuperação de senha por e-mail (sem revelar existência de e-mail).
"""

import time

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, password_validation
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from django.utils.encoding import DjangoUnicodeDecodeError, force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from core.api.exceptions import BusinessError
from organizations.models import Membership, Organization

User = get_user_model()

_FAIL_KEY = "login-fail::{email}"
_LOCK_KEY = "login-lock::{email}"


@transaction.atomic
def register_with_organization(
    *,
    email: str,
    password: str,
    first_name: str,
    last_name: str = "",
    organization_name: str,
    vertical: str,
    organization_phone: str = "",
) -> tuple:
    """User + Organization (slug automático) + Membership OWNER numa transação."""
    user = User.objects.create_user(
        email=email, password=password, first_name=first_name, last_name=last_name
    )
    from django.utils.text import slugify

    from billing.models import Plan, PlanTier, Subscription
    from catalog.seed_data import seed_catalog

    slug_base = f"{slugify(organization_name)}-{slugify(first_name)}"[:60].strip("-") or "salao"
    slug, suffix = slug_base, 2
    while Organization.objects.filter(slug=slug).exists():
        ending = f"-{suffix}"
        slug = f"{slug_base[:60 - len(ending)]}{ending}"
        suffix += 1
    tema_cor = "#2563EB" if vertical == Organization.Vertical.BARBEARIA else "#8B5CF6"
    organization = Organization.objects.create(
        name=organization_name,
        slug=slug,
        vertical=vertical,
        tema_cor=tema_cor,
        phone=organization_phone,
    )
    Subscription.objects.get_or_create(
        organization=organization,
        defaults={"plan": Plan.objects.get(tier=PlanTier.FREE)},
    )
    seed_catalog(organization)
    Membership.objects.create(user=user, organization=organization, role=Membership.Role.OWNER)
    return user, organization


def check_login_allowed(email: str):
    """None = liberado; caso contrário, segundos restantes de bloqueio."""
    if email is None:
        return None
    until = cache.get(_LOCK_KEY.format(email=email.lower()))
    if until is None:
        return None
    remaining = int(until - time.time())
    if remaining > 0:
        return remaining
    cache.delete(_LOCK_KEY.format(email=email.lower()))
    return None


def register_failed_login(email: str) -> None:
    """Acumula falhas por e-mail (janela = tempo de bloqueio) e trava no limite."""
    if email is None:
        return
    key = _FAIL_KEY.format(email=email.lower())
    failures = cache.get(key) or 0
    failures += 1
    if failures >= settings.LOGIN_MAX_FAILED_ATTEMPTS:
        cache.set(
            _LOCK_KEY.format(email=email.lower()),
            time.time() + settings.LOGIN_LOCKOUT_SECONDS,
            timeout=settings.LOGIN_LOCKOUT_SECONDS,
        )
        cache.delete(key)
    else:
        cache.set(key, failures, timeout=settings.LOGIN_LOCKOUT_SECONDS)


def clear_login_failures(email: str) -> None:
    if email is None:
        return
    cache.delete(_FAIL_KEY.format(email=email.lower()))
    cache.delete(_LOCK_KEY.format(email=email.lower()))


def authenticate_by_email(*, email: str, password: str):
    """Autentica por e-mail (USERNAME_FIELD) com e-mail em minúsculas."""
    return authenticate(email=email.strip().lower(), password=password)


def request_password_reset(email: str) -> None:
    """
    Envia o e-mail de reset apenas se o e-mail existir. A resposta HTTP é
    sempre a mesma — nunca revela se o e-mail está cadastrado.
    """
    user = User.objects.filter(email=email.strip().lower(), is_active=True).first()
    if user is None:
        return
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    reset_url = f"{settings.FRONTEND_URL.rstrip('/')}/resetar-senha/{uid}/{token}"
    send_mail(
        subject="Redefinir senha — Éclat Studio",
        message=_password_reset_email_body(user, reset_url),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )


def _password_reset_email_body(user, reset_url: str) -> str:
    from django.template.loader import render_to_string

    return render_to_string(
        "registration/password_reset_email.txt",
        {"user": user, "reset_url": reset_url},
    )


def confirm_password_reset(*, uidb64: str, token: str, new_password: str) -> None:
    """Valida uid/token, valida a senha forte e aplica o hash (Argon2)."""
    user = _decode_reset_user(uidb64, token)
    password_validation.validate_password(new_password, user=user)
    user.set_password(new_password)
    user.save(update_fields=["password"])


def _decode_reset_user(uidb64: str, token: str):
    try:
        user_id = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=user_id)
    except (User.DoesNotExist, ValueError, DjangoUnicodeDecodeError, TypeError):
        raise _invalid_reset() from None  # resposta genérica; nada leakado

    if not default_token_generator.check_token(user, token):
        raise _invalid_reset()
    return user


def _invalid_reset() -> Exception:
    from rest_framework.exceptions import ValidationError

    return ValidationError({"detail": ["Link inválido ou expirado. Solicite um novo."]})


def blacklist_refresh(token_string: str) -> None:
    """Invalida (blacklist) um refresh token no logout."""
    from rest_framework_simplejwt.exceptions import TokenError
    from rest_framework_simplejwt.tokens import RefreshToken

    try:
        token = RefreshToken(token_string)
    except TokenError as err:
        raise BusinessError("Refresh token inválido ou expirado.", code="invalid_refresh") from err
    token.blacklist()


def issue_tokens(user) -> "dict[str, str]":
    """Gera (access, refresh) com os claims de salão do usuário."""
    from core.api.jwt import TenantTokenObtainPairSerializer

    refresh = TenantTokenObtainPairSerializer.get_token(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}
