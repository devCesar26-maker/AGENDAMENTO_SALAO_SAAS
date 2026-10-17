"""Throttling: taxa por usuário; taxas específicas para auth e rota pública."""

from rest_framework.throttling import ScopedRateThrottle, SimpleRateThrottle, UserRateThrottle


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


class PublicBookingRateThrottle(SimpleRateThrottle):
    """API pública de reserva: sempre por IP, mesmo com credenciais anexadas."""

    scope = "public_booking"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}
