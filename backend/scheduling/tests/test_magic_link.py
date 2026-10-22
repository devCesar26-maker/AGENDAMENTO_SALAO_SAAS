"""Cobertura do link mágico: token, GET/POST públicos e isolamento por tenant."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from customers.models import Customer
from notifications.models import NotificationEvent
from notifications.tasks import send_appointment_confirmation
from scheduling.models import Appointment, AppointmentToken
from scheduling.services import create_appointment
from scheduling.tests.test_public_booking import make_public_schedule

BOOKING_DAY = datetime(2026, 10, 19, 9, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))


def make_customer(organization, **kwargs):
    defaults = {
        "organization": organization,
        "name": "Cliente mágico",
        "phone": "11944443333",
        "email": "cliente-magico@example.com",
    }
    defaults.update(kwargs)
    return Customer.objects.create(**defaults)


def make_appointment(organization, customer, service, professional):
    return create_appointment(
        organization=organization,
        customer=customer,
        items=[{"service": service, "professional": professional, "order": 0}],
        desired_start=BOOKING_DAY,
        membership=None,
    )


def schedule_for(org):
    _, service, professional = make_public_schedule(org)
    service.name = f"Serviço {org.slug}"
    service.save(update_fields=["name"])
    professional.name = f"Profissional {org.slug}"
    professional.save(update_fields=["name"])
    return service, professional


@pytest.mark.django_db
def test_agendamento_nasce_com_token_email_e_ida_para_papel(organization):
    customer = make_customer(organization)
    service, professional = schedule_for(organization)
    appointment = make_appointment(organization, customer, service, professional)

    assert appointment.tokens.filter(action=AppointmentToken.Action.VIEW).count() == 1
    assert NotificationEvent.objects.filter(
        appointment=appointment, kind=NotificationEvent.Kind.CONFIRMATION
    ).exists()


@pytest.mark.django_db
def test_get_token_valido_mostra_os_dados_corretos(api_client, organization):
    customer = make_customer(organization)
    service, professional = schedule_for(organization)
    appointment = make_appointment(organization, customer, service, professional)
    token = appointment.tokens.get()

    response = api_client.get(
        reverse("public-appointment-magic-link", kwargs={"token": token.token})
    )
    assert response.status_code == 200, response.json()
    payload = response.json()
    assert payload["status"] == appointment.status
    assert payload["organization_name"] == organization.name
    assert payload["customer_name"] == "Cliente mágico"
    assert payload["can_cancel"] is True
    assert [item["service"] for item in payload["items"]] == ["Serviço " + organization.slug]
    assert [item["professional"] for item in payload["items"]] == [
        "Profissional " + organization.slug
    ]
    assert payload["items"][0]["start_at"].startswith("2026-10-19T09:00:00")
    assert payload["expires_at"] == token.expires_at.isoformat()


@pytest.mark.django_db
def test_get_token_expirado_e_rejeitado_com_mensagem_clara(api_client, organization):
    customer = make_customer(organization)
    service, professional = schedule_for(organization)
    appointment = make_appointment(organization, customer, service, professional)
    token = appointment.tokens.get()
    AppointmentToken.objects.filter(pk=token.pk).update(
        expires_at=timezone.now() - timedelta(hours=1)
    )

    response = api_client.get(
        reverse("public-appointment-magic-link", kwargs={"token": token.token})
    )
    assert response.status_code == 410
    assert "expirou" in response.json()["detail"]

    canceled = api_client.post(
        reverse("public-appointment-magic-link-cancel", kwargs={"token": token.token})
    )
    assert canceled.status_code == 410
    appointment.refresh_from_db()
    assert appointment.status == Appointment.Status.SCHEDULED


@pytest.mark.django_db
def test_get_token_inexistente_retorna_404_sem_jargao(api_client):
    response = api_client.get(
        reverse("public-appointment-magic-link", kwargs={"token": "nao-existe"})
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Este link é inválido."


@pytest.mark.django_db
def test_cancelar_via_token_muda_status_marca_uso_e_fila_notificacao(api_client, organization):
    customer = make_customer(organization)
    service, professional = schedule_for(organization)
    appointment = make_appointment(organization, customer, service, professional)
    token = appointment.tokens.get()

    response = api_client.post(
        reverse("public-appointment-magic-link-cancel", kwargs={"token": token.token})
    )
    assert response.status_code == 200, response.json()
    appointment.refresh_from_db()
    token.refresh_from_db()
    assert appointment.status == Appointment.Status.CANCELED
    assert token.used_at is not None
    assert response.json()["status"] == Appointment.Status.CANCELED
    assert response.json()["can_cancel"] is False
    assert NotificationEvent.objects.filter(
        appointment=appointment, kind=NotificationEvent.Kind.CANCELLATION
    ).exists()


@pytest.mark.django_db
def test_token_ja_usado_e_rejeitado_no_get_e_no_cancelamento(api_client, organization):
    customer = make_customer(organization)
    service, professional = schedule_for(organization)
    appointment = make_appointment(organization, customer, service, professional)
    token = appointment.tokens.get()

    first = api_client.post(
        reverse("public-appointment-magic-link-cancel", kwargs={"token": token.token})
    )
    assert first.status_code == 200

    second = api_client.post(
        reverse("public-appointment-magic-link-cancel", kwargs={"token": token.token})
    )
    assert second.status_code == 410
    assert "já foi utilizado" in second.json()["detail"]

    view = api_client.get(reverse("public-appointment-magic-link", kwargs={"token": token.token}))
    assert view.status_code == 410
    assert "já foi utilizado" in view.json()["detail"]


@pytest.mark.django_db
def test_agendamento_concluido_nao_pode_ser_cancelado_via_token(api_client, organization):
    customer = make_customer(organization)
    service, professional = schedule_for(organization)
    appointment = make_appointment(organization, customer, service, professional)
    token = appointment.tokens.get()
    Appointment.objects.filter(pk=appointment.pk).update(status=Appointment.Status.COMPLETED)

    response = api_client.post(
        reverse("public-appointment-magic-link-cancel", kwargs={"token": token.token})
    )
    assert response.status_code == 409
    appointment.refresh_from_db()
    assert appointment.status == Appointment.Status.COMPLETED
    token.refresh_from_db()
    assert token.used_at is None


@pytest.mark.django_db
def test_isolamento_de_tenant_no_link_magico(api_client, organization, other_organization):
    customer = make_customer(organization)
    service, professional = schedule_for(organization)
    appointment = make_appointment(organization, customer, service, professional)
    token = appointment.tokens.get()

    customer_b = make_customer(other_organization, name="Cliente salão B", phone="11955552222")
    service_b, professional_b = schedule_for(other_organization)
    appointment_b = make_appointment(other_organization, customer_b, service_b, professional_b)
    token_b = appointment_b.tokens.get()

    view = api_client.get(reverse("public-appointment-magic-link", kwargs={"token": token.token}))
    assert view.status_code == 200
    body = view.json()
    assert f"Serviço {organization.slug}" in str(body["items"])
    assert other_organization.name not in str(body["items"])
    assert f"Serviço {other_organization.slug}" not in str(body["items"])
    assert "Cliente salão B" not in str(body)

    cancel = api_client.post(
        reverse("public-appointment-magic-link-cancel", kwargs={"token": token.token})
    )
    assert cancel.status_code == 200
    appointment_b.refresh_from_db()
    token_b.refresh_from_db()
    assert appointment_b.status == Appointment.Status.SCHEDULED
    # Resposta do cancelamento também carrega apenas dados da organização A.
    assert f"Serviço {other_organization.slug}" not in str(cancel.json()["items"])


@pytest.mark.django_db
def test_link_magico_aparece_no_email_de_confirmacao(api_client, organization):
    customer = make_customer(organization)
    service, professional = schedule_for(organization)
    appointment = make_appointment(organization, customer, service, professional)
    token = appointment.tokens.get()

    sent = send_appointment_confirmation.run(appointment.pk)
    assert sent is True
    assert mail.outbox, "e-mail de confirmação deveria ter sido enviado"
    assert f"/a/{token.token}" in mail.outbox[0].body
    assert mail.outbox[0].to == [customer.email]
