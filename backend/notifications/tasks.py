"""Tarefas assíncronas para e-mails de agendamento e lista de espera."""

from datetime import timedelta
from zoneinfo import ZoneInfo

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail, send_mass_mail
from django.template.loader import render_to_string
from django.utils import timezone

from notifications.models import WaitlistEntry
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


@shared_task
def send_appointment_reminders():
    """Envia em lote lembretes de 24h sem repetir agendamentos já notificados."""
    now = timezone.now()
    window_start = now + timedelta(hours=23, minutes=50)
    window_end = now + timedelta(hours=24, minutes=10)
    appointments = list(reminder_candidates(window_start, window_end))
    messages = []
    for appointment in appointments:
        context = _appointment_email_context(appointment)
        subject = (
            render_to_string("notifications/email/appointment_reminder_subject.txt", context)
            .strip()
            .replace("\n", " ")
        )
        body = render_to_string("notifications/email/appointment_reminder.txt", context)
        messages.append((subject, body, settings.DEFAULT_FROM_EMAIL, [appointment.customer.email]))
    if not messages:
        return 0
    send_mass_mail(messages, fail_silently=False)
    Appointment.objects.filter(pk__in=[item.pk for item in appointments]).update(
        reminder_sent_at=now
    )
    return len(messages)


@shared_task
def send_appointment_cancellation(appointment_id):
    appointment = appointment_for_notification(appointment_id)
    if appointment is None:
        return False
    return _send_appointment_email(
        appointment,
        subject_template="notifications/email/appointment_cancellation_subject.txt",
        body_template="notifications/email/appointment_cancellation.txt",
    )


@shared_task
def notify_waitlist_for_canceled_appointment(appointment_id):
    appointment = appointment_for_notification(appointment_id)
    if appointment is None:
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
