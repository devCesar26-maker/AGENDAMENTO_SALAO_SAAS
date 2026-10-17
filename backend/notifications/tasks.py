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
from notifications.models import NotificationEvent, WaitlistEntry
from notifications.selectors import (
    appointment_for_notification,
    reminder_candidates,
    waitlist_matches_for_open_slot,
)
from scheduling.models import Appointment


def _appointment_email_context(appointment):
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
    }


def _send_appointment_email(appointment, *, subject_template, body_template):
    if not appointment.customer.email:
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
            "recipient": appointment.customer.email,
            "subject": subject,
            "body": body,
        },
    )
    if claim_id is None:
        return False
    delivered = send_mail(
        subject, body, settings.DEFAULT_FROM_EMAIL, [appointment.customer.email]
    )
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
    for appointment in appointments:
        context = _appointment_email_context(appointment)
        subject = (
            render_to_string(
                "notifications/email/appointment_reminder_subject.txt", context
            )
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
                    "recipient": appointment.customer.email,
                    "subject": subject,
                    "body": body,
                },
            )
        )
    claims = claim_side_effects(
        organization=appointments[0].organization,
        context="notification_reminder",
        effects=[{"key": str(row[0].pk), "data": row[3]} for row in messages],
    )
    claimed = [(row, claims[str(row[0].pk)]) for row in messages]
    duplicate_ids = [row[0].pk for row, claim_id in claimed if claim_id is None]
    if duplicate_ids:
        Appointment.objects.filter(
            pk__in=duplicate_ids, reminder_sent_at__isnull=True
        ).update(reminder_sent_at=now)
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
                subject, body, settings.DEFAULT_FROM_EMAIL, [appointment.customer.email]
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
            and (
                entry.professional_id is None
                or entry.professional_id == item.professional_id
            )
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
            render_to_string(
                "notifications/email/waitlist_opening_subject.txt", context
            )
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
        delivered = send_mail(
            subject, body, settings.DEFAULT_FROM_EMAIL, [entry.customer.email]
        )
        if delivered != 1:
            raise RuntimeError(
                "O backend de e-mail não confirmou o aviso da lista de espera."
            )
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
                | Q(
                    state=NotificationEvent.State.PROCESSING, locked_at__lt=stale_before
                )
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
