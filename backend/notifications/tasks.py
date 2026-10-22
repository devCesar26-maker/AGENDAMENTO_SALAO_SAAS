"""Tarefas assíncronas para e-mails de agendamento e lista de espera."""

from datetime import timedelta
from zoneinfo import ZoneInfo

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import F, Q
from django.template.loader import render_to_string
from django.utils import timezone

from core.idempotency import (
    claim_side_effect,
    claim_side_effects,
    complete_side_effect,
    complete_side_effects,
    release_side_effects,
)
from notifications.models import NotificationEvent, WaitlistEntry, WaitlistOffer
from notifications.selectors import (
    appointment_for_notification,
    reminder_candidates,
    waitlist_matches_for_open_slot,
)
from scheduling.models import Appointment


def _appointment_email_context(appointment, magic_token=None):
    tz = ZoneInfo(appointment.organization.timezone)
    items = [
        {
            "service": item.service.name,
            "professional": item.professional.name,
            "start": timezone.localtime(item.start_at, tz),
            "end": timezone.localtime(item.end_at, tz),
        }
        for item in appointment.items.all()
    ]
    return {
        "organization": appointment.organization,
        "customer": appointment.customer,
        "appointment": appointment,
        "items": items,
        "first_item": items[0] if items else None,
        "manage_link": _magic_link_for(appointment, magic_token),
    }


def _magic_link_for(appointment, token=None):
    """Link mágico (visualizar/cancelar) gerado junto com a criação do agendamento."""
    from scheduling.services import ensure_magic_link_token

    token = token if token is not None else ensure_magic_link_token(appointment)
    return f"{settings.FRONTEND_URL.rstrip('/')}/a/{token.token}"


def _send_appointment_email(appointment, *, subject_template, body_template):
    recipient = appointment.customer.notification_contact.email
    if not recipient:
        return False
    context = _appointment_email_context(appointment)
    subject = render_to_string(subject_template, context).strip().replace("\n", " ")
    body = render_to_string(body_template, context)
    notification_type = subject_template.rsplit("/", 1)[-1].replace("_subject.txt", "")
    claim_id = claim_side_effect(
        organization=appointment.organization,
        context=f"notification_{notification_type}",
        key=str(appointment.pk),
        data={
            "recipient": recipient,
            "subject": subject,
            "body": body,
        },
    )
    if claim_id is None:
        return False
    delivered = send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient])
    if delivered != 1:
        raise RuntimeError("O backend de e-mail não confirmou a notificação.")
    complete_side_effect(claim_id)
    return True


@shared_task
def send_appointment_confirmation(appointment_id):
    appointment = appointment_for_notification(appointment_id)
    if appointment is None or appointment.status == Appointment.Status.CANCELED:
        return False
    return _send_appointment_email(
        appointment,
        subject_template="notifications/email/appointment_confirmation_subject.txt",
        body_template="notifications/email/appointment_confirmation.txt",
    )


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def send_appointment_reminders():
    """Envia em lote lembretes de 24h sem repetir agendamentos já notificados."""
    now = timezone.now()
    window_start = now + timedelta(hours=23, minutes=50)
    window_end = now + timedelta(hours=24, minutes=10)
    appointments = list(reminder_candidates(window_start, window_end).order_by("pk"))
    by_organization = {}
    for appointment in appointments:
        by_organization.setdefault(appointment.organization_id, []).append(appointment)
    return sum(_send_reminder_batch(group, now) for group in by_organization.values())


def _send_reminder_batch(appointments, now):
    messages = []
    from scheduling.services import tokens_for_appointments

    # Tokens do link mágico em UMA consulta para o lote inteiro (sem N+1).
    magic_tokens = tokens_for_appointments(
        [appointment.pk for appointment in appointments],
        appointments[0].organization,
    )
    for appointment in appointments:
        recipient = appointment.customer.notification_contact.email
        if not recipient:
            continue
        context = _appointment_email_context(
            appointment, magic_token=magic_tokens.get(appointment.pk)
        )
        subject = (
            render_to_string("notifications/email/appointment_reminder_subject.txt", context)
            .strip()
            .replace("\n", " ")
        )
        body = render_to_string("notifications/email/appointment_reminder.txt", context)
        messages.append(
            (
                appointment,
                subject,
                body,
                {
                    "recipient": recipient,
                    "subject": subject,
                    "body": body,
                },
            )
        )
    if not messages:
        return 0
    claims = claim_side_effects(
        organization=appointments[0].organization,
        context="notification_reminder",
        effects=[{"key": str(row[0].pk), "data": row[3]} for row in messages],
    )
    claimed = [(row, claims[str(row[0].pk)]) for row in messages]
    duplicate_ids = [row[0].pk for row, claim_id in claimed if claim_id is None]
    if duplicate_ids:
        Appointment.objects.filter(pk__in=duplicate_ids, reminder_sent_at__isnull=True).update(
            reminder_sent_at=now
        )
    sent_ids = []
    sent_claims = []
    pending_claims = [claim_id for _, claim_id in claimed if claim_id is not None]
    for row, claim_id in claimed:
        if claim_id is None:
            continue
        appointment, subject, body, _ = row
        pending_claims.remove(claim_id)
        try:
            delivered = send_mail(
                subject,
                body,
                settings.DEFAULT_FROM_EMAIL,
                [appointment.customer.notification_contact.email],
            )
            if delivered != 1:
                raise RuntimeError("O backend de e-mail não confirmou o lembrete.")
        except Exception:
            complete_side_effects(sent_claims)
            # A claim da mensagem tentada fica persistida: o SMTP pode ter aceitado
            # a mensagem mesmo se a conexão falhou antes da confirmação local.
            release_side_effects(pending_claims)
            if sent_ids:
                Appointment.objects.filter(pk__in=sent_ids).update(reminder_sent_at=now)
            raise
        sent_claims.append(claim_id)
        sent_ids.append(appointment.pk)
    if sent_claims:
        complete_side_effects(sent_claims)
    if sent_ids:
        Appointment.objects.filter(pk__in=sent_ids).update(reminder_sent_at=now)
    return len(sent_ids)


@shared_task
def send_appointment_cancellation(appointment_id):
    appointment = appointment_for_notification(appointment_id)
    if appointment is None or appointment.status != Appointment.Status.CANCELED:
        return False
    return _send_appointment_email(
        appointment,
        subject_template="notifications/email/appointment_cancellation_subject.txt",
        body_template="notifications/email/appointment_cancellation.txt",
    )


def _send_message_once(*, organization, context, key, recipient, subject, body):
    if not recipient:
        return False
    claim_id = claim_side_effect(
        organization=organization,
        context=context,
        key=key,
        data={"recipient": recipient, "subject": subject, "body": body},
    )
    if claim_id is None:
        return False
    delivered = send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient])
    if delivered != 1:
        raise RuntimeError("O backend de e-mail não confirmou a notificação.")
    complete_side_effect(claim_id)
    return True


@shared_task
def send_waitlist_priority_offer(offer_id):
    offer = (
        WaitlistOffer.objects.select_related(
            "organization",
            "entry",
            "entry__customer",
            "entry__customer__responsavel",
            "appointment_item",
            "appointment_item__service",
            "appointment_item__professional",
            "appointment_item__appointment",
        )
        .filter(pk=offer_id)
        .first()
    )
    if offer is None or not offer.is_active:
        return False
    recipient = offer.entry.customer.notification_contact.email
    item = offer.appointment_item
    tz = ZoneInfo(offer.organization.timezone)
    context = {
        "organization": offer.organization,
        "customer": offer.entry.customer,
        "service": item.service,
        "professional": item.professional,
        "start": timezone.localtime(item.start_at, tz),
        "expires_at": timezone.localtime(offer.expires_at, tz),
        "priority_url": f"{settings.FRONTEND_URL.rstrip('/')}/prioridade/{offer.token}",
    }
    subject = (
        render_to_string("notifications/email/waitlist_priority_subject.txt", context)
        .strip()
        .replace("\n", " ")
    )
    body = render_to_string("notifications/email/waitlist_priority.txt", context)
    return _send_message_once(
        organization=offer.organization,
        context="notification_waitlist_priority",
        key=str(offer.pk),
        recipient=recipient,
        subject=subject,
        body=body,
    )


@shared_task
def send_rating_request(appointment_id):
    appointment = appointment_for_notification(appointment_id)
    if appointment is None or appointment.status != Appointment.Status.COMPLETED:
        return False
    from scheduling.services import ensure_rating_token

    token = ensure_rating_token(appointment)
    recipient = appointment.customer.notification_contact.email
    context = _appointment_email_context(appointment)
    context.update(
        {
            "rating_url": f"{settings.FRONTEND_URL.rstrip('/')}/avaliar/{token.token}",
            "rating_expires_at": token.expires_at,
        }
    )
    subject = (
        render_to_string("notifications/email/rating_request_subject.txt", context)
        .strip()
        .replace("\n", " ")
    )
    body = render_to_string("notifications/email/rating_request.txt", context)
    return _send_message_once(
        organization=appointment.organization,
        context="notification_rating_request",
        key=str(appointment.pk),
        recipient=recipient,
        subject=subject,
        body=body,
    )


@shared_task
def send_recurring_suggestion(appointment_id):
    appointment = appointment_for_notification(appointment_id)
    if appointment is None or appointment.status != Appointment.Status.SUGGESTED:
        return False
    from scheduling.models import AppointmentToken
    from scheduling.services import ensure_appointment_token

    token = ensure_appointment_token(
        appointment,
        AppointmentToken.Action.CONFIRM,
        expires_at=appointment.suggestion_expires_at,
    )
    recipient = appointment.customer.notification_contact.email
    context = _appointment_email_context(appointment)
    context.update(
        {
            "suggestion_url": f"{settings.FRONTEND_URL.rstrip('/')}/sugestao/{token.token}",
            "suggestion_expires_at": appointment.suggestion_expires_at,
        }
    )
    subject = (
        render_to_string("notifications/email/recurring_suggestion_subject.txt", context)
        .strip()
        .replace("\n", " ")
    )
    body = render_to_string("notifications/email/recurring_suggestion.txt", context)
    return _send_message_once(
        organization=appointment.organization,
        context="notification_recurring_suggestion",
        key=str(appointment.pk),
        recipient=recipient,
        subject=subject,
        body=body,
    )


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def expire_waitlist_offers(batch_size=100):
    """Expira holds vencidos e oferece o mesmo item ao próximo da fila."""
    from notifications.services import offer_next_waitlist_entry_for_item

    now = timezone.now()
    with transaction.atomic():
        offers = list(
            WaitlistOffer.objects.select_for_update(skip_locked=True)
            .filter(status=WaitlistOffer.Status.ACTIVE, expires_at__lte=now)
            .select_related("appointment_item")
            .order_by("expires_at")[:batch_size]
        )
        offer_ids = [offer.pk for offer in offers]
        WaitlistOffer.objects.filter(pk__in=offer_ids).update(status=WaitlistOffer.Status.EXPIRED)
    for offer in offers:
        offer_next_waitlist_entry_for_item(offer.appointment_item)
    return len(offers)


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def expire_suggested_appointments(batch_size=100):
    """Libera sugestões não confirmadas após o prazo, sem cobrar nem notificar o cliente."""
    from notifications.services import start_waitlist_priority_for_appointment
    from scheduling.models import AppointmentToken

    now = timezone.now()
    with transaction.atomic():
        appointments = list(
            Appointment.objects.select_for_update(skip_locked=True)
            .filter(
                status=Appointment.Status.SUGGESTED,
                suggestion_expires_at__lte=now,
            )
            .order_by("suggestion_expires_at")[:batch_size]
        )
        ids = [appointment.pk for appointment in appointments]
        Appointment.objects.filter(pk__in=ids).update(
            status=Appointment.Status.CANCELED,
            suggestion_expires_at=None,
        )
        AppointmentToken.objects.filter(
            appointment_id__in=ids, action=AppointmentToken.Action.CONFIRM, used_at__isnull=True
        ).update(used_at=now)
    for appointment in appointments:
        appointment.status = Appointment.Status.CANCELED
        start_waitlist_priority_for_appointment(appointment)
    return len(appointments)


@shared_task
def notify_waitlist_for_canceled_appointment(appointment_id):
    appointment = appointment_for_notification(appointment_id)
    if appointment is None or appointment.status != Appointment.Status.CANCELED:
        return 0

    tz = ZoneInfo(appointment.organization.timezone)
    service_items = list(appointment.items.all())
    entries = list(waitlist_matches_for_open_slot(appointment, service_items))
    matching_items = {}
    for entry in entries:
        matching_items[entry.pk] = next(
            item
            for item in service_items
            if item.service_id == entry.service_id
            and timezone.localtime(item.start_at, tz).date() == entry.desired_date
            and (entry.professional_id is None or entry.professional_id == item.professional_id)
        )

    sent_at = timezone.now()
    sent = 0
    for entry in entries:
        item = matching_items[entry.pk]
        start = timezone.localtime(item.start_at, tz)
        context = {
            "entry": entry,
            "organization": appointment.organization,
            "customer": entry.customer,
            "service": item.service,
            "professional": item.professional,
            "start": start,
            "booking_url": f"{settings.FRONTEND_URL.rstrip('/')}/b/{appointment.organization.slug}",
        }
        subject = (
            render_to_string("notifications/email/waitlist_opening_subject.txt", context)
            .strip()
            .replace("\n", " ")
        )
        body = render_to_string("notifications/email/waitlist_opening.txt", context)
        claim_id = claim_side_effect(
            organization=appointment.organization,
            context="notification_waitlist_opening",
            key=f"{appointment.pk}:{entry.pk}",
            data={"recipient": entry.customer.email, "subject": subject, "body": body},
        )
        if claim_id is None:
            WaitlistEntry.objects.filter(pk=entry.pk, notified_at__isnull=True).update(
                notified_at=sent_at
            )
            continue
        delivered = send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [entry.customer.email])
        if delivered != 1:
            raise RuntimeError("O backend de e-mail não confirmou o aviso da lista de espera.")
        complete_side_effect(claim_id)
        WaitlistEntry.objects.filter(pk=entry.pk, notified_at__isnull=True).update(
            notified_at=sent_at
        )
        sent += 1
    return sent


@shared_task
def dispatch_notification_outbox(batch_size=50):
    """Entrega eventos já persistidos; broker/SMTP indisponível não desfaz requests."""
    now = timezone.now()
    stale_before = now - timedelta(minutes=10)
    with transaction.atomic():
        events = list(
            NotificationEvent.objects.select_for_update(skip_locked=True)
            .filter(
                Q(state=NotificationEvent.State.PENDING, available_at__lte=now)
                | Q(state=NotificationEvent.State.PROCESSING, locked_at__lt=stale_before)
            )
            .order_by("created_at")[:batch_size]
        )
        event_ids = [event.pk for event in events]
        NotificationEvent.objects.filter(pk__in=event_ids).update(
            state=NotificationEvent.State.PROCESSING,
            locked_at=now,
            attempts=F("attempts") + 1,
        )

    delivered = 0
    for event_id in event_ids:
        event = NotificationEvent.objects.select_related("appointment").get(pk=event_id)
        try:
            appointment_id = event.appointment_id
            if event.kind == NotificationEvent.Kind.CONFIRMATION:
                send_appointment_confirmation.run(appointment_id)
            elif event.kind == NotificationEvent.Kind.CANCELLATION:
                send_appointment_cancellation.run(appointment_id)
            elif event.kind == NotificationEvent.Kind.WAITLIST_OPENING:
                notify_waitlist_for_canceled_appointment.run(appointment_id)
            elif event.kind == NotificationEvent.Kind.WAITLIST_PRIORITY:
                if event.waitlist_offer_id is None:
                    raise ValueError("Oferta prioritária sem referência.")
                send_waitlist_priority_offer.run(event.waitlist_offer_id)
            elif event.kind == NotificationEvent.Kind.RATING_REQUEST:
                send_rating_request.run(appointment_id)
            elif event.kind == NotificationEvent.Kind.RECURRING_SUGGESTION:
                send_recurring_suggestion.run(appointment_id)
            else:
                raise ValueError("Tipo de notificação desconhecido.")
        except Exception as error:
            delay = min(3600, 30 * (2 ** min(event.attempts, 7)))
            NotificationEvent.objects.filter(pk=event_id).update(
                state=NotificationEvent.State.PENDING,
                available_at=now + timedelta(seconds=delay),
                locked_at=None,
                last_error=type(error).__name__,
            )
            continue
        NotificationEvent.objects.filter(pk=event_id).update(
            state=NotificationEvent.State.SENT,
            sent_at=timezone.now(),
            locked_at=None,
            last_error="",
        )
        delivered += 1
    return delivered
