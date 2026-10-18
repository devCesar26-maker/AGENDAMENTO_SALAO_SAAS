"""
Sanitização de campos de texto livre contra XSS (backend).

Campos como observações do cliente e descrição do serviço são TEXTO SIMPLES:
a API remove todas as tags HTML (de forma idempotente, contra vetores que
"reabrem" tags após o primeiro passe) e normaliza espaçamento. A renderização no
frontend deve continuar usando interpolação de texto (nunca innerHTML) —
defesa em profundidade aplicada na escrita **e** na leitura.

`SANITIZE_ALLOWLIST_TAGS` (settings) permanece reservado para um sanitizador
de HTML rico futuro (bleach); aqui só entra texto simples, sem exceções.
"""

import re

from django.utils.html import strip_tags

_MULTIPLE_SPACES = re.compile(r"[ \t\f\v]+")
_MULTIPLE_BLANK_LINES = re.compile(r"\n{3,}")


def sanitize_free_text(value: str | None) -> str:
    """
    Normaliza texto livre: remove tags HTML até estabilizar, colapsa espaços,
    preserva quebras de linha. Idempotente e seguro re-consumir a própria saída.
    """
    if not value:
        return ""
    cleaned = value
    for _ in range(5):  # strip_tags não é idempotente por si só ("<scr<script>ipt>")
        stripped = strip_tags(cleaned)
        if stripped == cleaned:
            break
        cleaned = stripped
    cleaned = "\n".join(
        _MULTIPLE_SPACES.sub(" ", line).strip() for line in cleaned.splitlines()
    )
    cleaned = _MULTIPLE_BLANK_LINES.sub("\n\n", cleaned)
    return cleaned.strip()
