"""Tarefas assíncronas para e-mails de agendamento e lista de espera."""

from datetime import timedelta
from zoneinfo import ZoneInfo

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail, send_mass_mail
from django.db import transaction
from django.db.models import F, Q
from django.template.loader import render_to_string
from django.utils import timezone

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
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [appointment.customer.email])
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
    with transaction.atomic():
        appointments = list(
            reminder_candidates(window_start, window_end)
            .select_for_update(skip_locked=True)
            .order_by("pk")
        )
        messages = []
        for appointment in appointments:
            context = _appointment_email_context(appointment)
            subject = (
                render_to_string("notifications/email/appointment_reminder_subject.txt", context)
                .strip()
                .replace("\n", " ")
            )
            body = render_to_string("notifications/email/appointment_reminder.txt", context)
            messages.append(
                (subject, body, settings.DEFAULT_FROM_EMAIL, [appointment.customer.email])
            )
        if not messages:
            return 0
        delivered = send_mass_mail(messages, fail_silently=False)
        if delivered != len(messages):
            raise RuntimeError("O backend de e-mail não confirmou todos os lembretes.")
        Appointment.objects.filter(pk__in=[item.pk for item in appointments]).update(
            reminder_sent_at=now
        )
        return len(messages)


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
            and (entry.professional_id is None or entry.professional_id == item.professional_id)
        )

    sent_at = timezone.now()
    messages = []
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
        messages.append((subject, body, settings.DEFAULT_FROM_EMAIL, [entry.customer.email]))

    if not messages:
        return 0
    send_mass_mail(messages, fail_silently=False)
    WaitlistEntry.objects.filter(pk__in=[entry.pk for entry in entries]).update(notified_at=sent_at)
    return len(messages)


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
