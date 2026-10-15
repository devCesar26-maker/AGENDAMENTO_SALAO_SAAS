"""Throttling: taxa por usuário; taxas específicas para auth e rota pública."""

from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle


class RoleUserRateThrottle(UserRateThrottle):
    """Throttle padrão por usuário autenticado (anon cai no fallback do DRF)."""

    scope = "user"


class AuthRateThrottle(ScopedRateThrottle):
    """ "
    Login/registro/recuperação de senha: mais restritivo (anti brute force).
    IMPORTANTE: ScopedRateThrottle lê o escopo de `view.throttle_scope` —
    views que usam esta classe precisam definir `throttle_scope = "auth"`.
    """

    scope = "auth"


class PublicBookingRateThrottle(ScopedRateThrottle):
    """Página pública de reserva: por IP, sem sessão/cookie."""

    scope = "public_booking"
