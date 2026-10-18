"""
Formato único de erro da API:

    {"error": {"code": "validation_error", "detail": "...", "fields": {...}}}

Códigos estáveis permitem o frontend tratar erros sem depender de mensagens.
"""

import logging

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.http import Http404, JsonResponse
from rest_framework import exceptions, status
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger("ecalt")

_ERROR_CODES = {
    "Http404": "not_found",
    "NotFound": "not_found",
    "MethodNotAllowed": "method_not_allowed",
    "NotAuthenticated": "not_authenticated",
    "AuthenticationFailed": "authentication_failed",
    "PermissionDenied": "forbidden",
    "ParseError": "invalid_body",
    "ValidationError": "validation_error",
    "Throttled": "throttled",
}


def _normalize_detail(detail) -> str:
    """Normaliza detail de exceção DRF (pode ser str, lista ou dict com detail)."""
    if isinstance(detail, dict) and "detail" in detail:
        detail = detail["detail"]
    if isinstance(detail, (list, tuple)):
        detail = str(detail[0]) if detail else None
    return str(detail) if detail else "Erro na requisição."


def exception_handler(exc, context):
    """Converte exceções DRF/Django para o formato padronizado."""
    response = drf_exception_handler(exc, context)
    if response is None:
        return None  # 500; middleware loga e padroniza fora de DEBUG

    code = _ERROR_CODES.get(exc.__class__.__name__)
    if code is None:
        # Exceções de domínio (ex.: BusinessError) carregam código estável próprio:
        # prefira o code do detail (ex.: "last_owner", "category_in_use").
        detail_code = getattr(getattr(exc, "detail", None), "code", None)
        code = (
            detail_code if isinstance(detail_code, str) else getattr(exc, "default_code", "error")
        )
    detail = getattr(exc, "detail", None)
    if isinstance(detail, dict) and "detail" in detail:
        error_data = dict(detail)
        error_data["detail"] = _normalize_detail(error_data["detail"])
        for field in ("limit", "usage"):
            if field in error_data:
                error_data[field] = int(error_data[field])
        payload = {"error": {"code": code, **error_data}}
    else:
        payload = {"error": {"code": code, "detail": _normalize_detail(detail)}}

    if code == "validation_error" and isinstance(response.data, dict):
        if "detail" not in response.data:
            payload["error"]["fields"] = {
                field: err if isinstance(err, list) else [err]
                for field, err in response.data.items()
            }
            payload["error"]["detail"] = "Verifique os campos informados."
        else:
            payload["error"]["detail"] = _normalize_detail(response.data["detail"])

    if code == "throttled" and getattr(exc, "wait", None):
        payload["error"]["detail"] = f"Muitas tentativas. Tente novamente em {int(exc.wait)}s."
        response["Retry-After"] = str(int(exc.wait))

    response.data = payload
    return response


class ExceptionFormatMiddleware:
    """
    Rede de segurança para exceções não tratadas em rotas /api/: converte para
    JSON no formato padrão (404 de objeto, PermissionDenied e 500 genérico).
    Em DEBUG, deixa o Django propagar para o traceback do dev server.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        from django.conf import settings

        if not request.path.startswith("/api/") or settings.DEBUG:
            return None

        if isinstance(exception, (Http404, ObjectDoesNotExist)):
            return JsonResponse(
                {"error": {"code": "not_found", "detail": "Recurso não encontrado."}},
                status=status.HTTP_404_NOT_FOUND,
            )
        if isinstance(exception, PermissionDenied):
            return JsonResponse(
                {"error": {"code": "forbidden", "detail": "Acesso negado."}},
                status=status.HTTP_403_FORBIDDEN,
            )
        logger.exception("Erro não tratado em %s %s", request.method, request.path)
        return JsonResponse(
            {
                "error": {
                    "code": "internal_error",
                    "detail": "Erro interno. Tente novamente.",
                }
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class BusinessError(exceptions.APIException):
    """Erro de regra de negócio com código estável (ex.: plano excedido)."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Operação não permitida."
    default_code = "business_error"

    def __init__(self, detail=None, code=None, http_status=None):
        if http_status is not None:
            self.status_code = http_status
        super().__init__(detail=detail, code=code)
