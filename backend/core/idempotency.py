"""Reusable request and side-effect idempotency primitives."""

import hashlib
import json
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from core.models import IdempotencyKey
from organizations.models import Organization


class IdempotencyConflict(Exception):
    """A key was reused for a different request or is already being processed."""


def _scope_digest(organization, context, key):
    scope = [organization.pk if organization else None, context, key]
    return hashlib.sha256(json.dumps(scope, separators=(",", ":")).encode()).hexdigest()


def fingerprint(value):
    """Stable SHA-256 fingerprint for validated request data."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _get_or_create_locked(*, organization, context, key, request_fingerprint, ttl):
    digest = _scope_digest(organization, context, key)
    defaults = {
        "key": key,
        "organization": organization,
        "context": context,
        "request_fingerprint": request_fingerprint,
        "expires_at": timezone.now() + ttl,
    }
    record, created = IdempotencyKey.objects.get_or_create(scope_digest=digest, defaults=defaults)
    record = IdempotencyKey.objects.select_for_update().get(pk=record.pk)
    if not created and record.expires_at <= timezone.now():
        for field, value in defaults.items():
            setattr(record, field, value)
        record.state = IdempotencyKey.State.PROCESSING
        record.result = None
        record.save()
        created = True
    if not created and record.request_fingerprint != request_fingerprint:
        raise IdempotencyConflict("Esta chave de idempotência já foi usada com outros dados.")
    return record, created


def execute_idempotently(*, organization, context, key, data, operation, ttl=timedelta(hours=48)):
    """Run and persist an operation in the same transaction as its result."""
    with transaction.atomic():
        record, created = _get_or_create_locked(
            organization=organization,
            context=context,
            key=key,
            request_fingerprint=fingerprint(data),
            ttl=ttl,
        )
        if not created:
            if record.state == IdempotencyKey.State.COMPLETED:
                return record.result, True
            raise IdempotencyConflict("Uma solicitação com esta chave ainda está em andamento.")

        result = operation()
        record.result = result
        record.state = IdempotencyKey.State.COMPLETED
        record.save(update_fields=("result", "state"))
        return result, False


def claim_side_effect(*, organization, context, key, data, ttl=timedelta(days=30)):
    """Persist a notification claim before SMTP so a crashed retry won't resend."""
    return claim_side_effects(
        organization=organization,
        context=context,
        effects=[{"key": key, "data": data}],
        ttl=ttl,
    )[key]


def claim_side_effects(*, organization, context, effects, ttl=timedelta(days=30)):
    """Claim multiple natural keys in a few queries, serialized per tenant."""
    now = timezone.now()
    digest_by_key = {
        effect["key"]: _scope_digest(organization, context, effect["key"]) for effect in effects
    }
    fingerprints = {effect["key"]: fingerprint(effect["data"]) for effect in effects}
    with transaction.atomic():
        # A tenant row is a stable mutex, including when no idempotency row exists yet.
        Organization.objects.select_for_update().only("pk").get(pk=organization.pk)
        records = list(
            IdempotencyKey.objects.select_for_update().filter(
                scope_digest__in=digest_by_key.values()
            )
        )
        expired = [record for record in records if record.expires_at <= now]
        if expired:
            IdempotencyKey.objects.filter(pk__in=[record.pk for record in expired]).delete()
        records = [record for record in records if record.expires_at > now]
        by_digest = {record.scope_digest: record for record in records}
        for key, digest in digest_by_key.items():
            record = by_digest.get(digest)
            if record and record.request_fingerprint != fingerprints[key]:
                raise IdempotencyConflict("A chave natural da notificação mudou de conteúdo.")
        to_create = [
            IdempotencyKey(
                key=key,
                scope_digest=digest_by_key[key],
                organization=organization,
                context=context,
                request_fingerprint=fingerprints[key],
                expires_at=now + ttl,
            )
            for key in digest_by_key
            if digest_by_key[key] not in by_digest
        ]
        created = IdempotencyKey.objects.bulk_create(to_create)
        ids_by_digest = {record.scope_digest: record.pk for record in created}
        return {key: ids_by_digest.get(digest) for key, digest in digest_by_key.items()}


def complete_side_effect(record_id):
    IdempotencyKey.objects.filter(pk=record_id).update(state=IdempotencyKey.State.COMPLETED)


def complete_side_effects(record_ids):
    IdempotencyKey.objects.filter(pk__in=record_ids).update(state=IdempotencyKey.State.COMPLETED)


def release_side_effects(record_ids):
    IdempotencyKey.objects.filter(pk__in=record_ids).delete()
