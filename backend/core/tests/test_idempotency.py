from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from core.idempotency import execute_idempotently
from core.models import IdempotencyKey


@pytest.mark.django_db
def test_comando_remove_chaves_expiradas_e_preserva_chaves_ativas():
    expired = IdempotencyKey.objects.create(
        key="old",
        scope_digest="1" * 64,
        context="test",
        request_fingerprint="a" * 64,
        expires_at=timezone.now() - timedelta(seconds=1),
    )
    active = IdempotencyKey.objects.create(
        key="new",
        scope_digest="2" * 64,
        context="test",
        request_fingerprint="b" * 64,
        expires_at=timezone.now() + timedelta(hours=1),
    )
    output = StringIO()

    call_command("cleanup_idempotency_keys", stdout=output)

    assert not IdempotencyKey.objects.filter(pk=expired.pk).exists()
    assert IdempotencyKey.objects.filter(pk=active.pk).exists()
    assert "1 chave(s) expirada(s) removida(s)" in output.getvalue()


@pytest.mark.django_db
def test_chave_e_resultado_sao_escopados_por_organizacao(
    organization, other_organization
):
    first, replayed = execute_idempotently(
        organization=organization,
        context="test_context",
        key="same-client-key",
        data={"value": 1},
        operation=lambda: {"appointment": 101},
    )
    tenant_b, tenant_b_replayed = execute_idempotently(
        organization=other_organization,
        context="test_context",
        key="same-client-key",
        data={"value": 2},
        operation=lambda: {"appointment": 202},
    )
    replay, was_replayed = execute_idempotently(
        organization=organization,
        context="test_context",
        key="same-client-key",
        data={"value": 1},
        operation=lambda: pytest.fail(
            "A operação idempotente foi executada novamente."
        ),
    )

    assert first == {"appointment": 101}
    assert replayed is False
    assert tenant_b == {"appointment": 202}
    assert tenant_b_replayed is False
    assert replay == first
    assert was_replayed is True
