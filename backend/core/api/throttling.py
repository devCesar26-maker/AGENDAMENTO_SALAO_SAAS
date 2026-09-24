"""Throttling: taxa por usuário; taxas específicas para auth e rota pública."""

from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle


class RoleUserRateThrottle(UserRateThrottle):
    """Throttle padrão por usuário autenticado (anon cai no fallback do DRF)."""

    scope = "user"


class AuthRateThrottle(ScopedRateThrottle):
    """Login/refresh/recuperação de senha: mais restritivo (anti brute force)."""

    scope = "auth"


class PublicBookingRateThrottle(ScopedRateThrottle):
    """Página pública de reserva: por IP, sem sessão/cookie."""

    scope = "public_booking"
