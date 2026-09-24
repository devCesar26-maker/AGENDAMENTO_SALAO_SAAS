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


def exception_handler(exc, context):
    """Converte exceções DRF/Django para o formato padronizado."""
    response = drf_exception_handler(exc, context)
    if response is None:
        return None  # 500; middleware loga e padroniza fora de DEBUG

    code = _ERROR_CODES.get(exc.__class__.__name__, "error")
    detail = getattr(response, "detail", None)
    payload = {"error": {"code": code, "detail": str(detail) if detail else "Erro na requisição."}}

    if code == "validation_error":
        # response.data: {campo: [erros]} ou lista de erros não-campo (detail)
        if isinstance(response.data, dict) and "detail" not in response.data:
            payload["error"]["fields"] = {
                field: err if isinstance(err, list) else [err]
                for field, err in response.data.items()
            }
            payload["error"]["detail"] = "Verifique os campos informados."
        elif isinstance(response.data, dict) and "detail" in response.data:
            payload["error"]["detail"] = str(response.data["detail"])

    if code == "throttled" and getattr(response, "wait", None):
        payload["error"]["detail"] = f"Muitas tentativas. Tente novamente em {int(response.wait)}s."
        response["Retry-After"] = str(int(response.wait))

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
            {"error": {"code": "internal_error", "detail": "Erro interno. Tente novamente."}},
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
