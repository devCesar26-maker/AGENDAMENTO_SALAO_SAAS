from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.db import close_old_connections, connection, connections
from django.urls import reverse

from accounts.factories import UserFactory
from catalog.factories import (
    ProfessionalFactory,
    ProfessionalServiceFactory,
    ServiceCategoryFactory,
    ServiceFactory,
    TimeOffFactory,
    WorkingHoursFactory,
)
from customers.factories import CustomerFactory
from organizations.factories import MembershipFactory, OrganizationFactory
from scheduling.models import Appointment, AppointmentItem
from scheduling.selectors import list_appointments
from scheduling.services import SlotUnavailable, calcular_slots_disponiveis, create_appointment

DAY = date(2026, 10, 19)  # segunda-feira


def setup_schedule(*, opens="09:00", closes="18:00", work_start=None, work_end=None):
    organization = OrganizationFactory(
        working_hours={"mon": [[opens, closes]]}, timezone="America/Sao_Paulo"
    )
    user = UserFactory()
    membership = MembershipFactory(organization=organization, user=user, role="OWNER")
    professional = ProfessionalFactory(organization=organization, user=user)
    category = ServiceCategoryFactory(organization=organization)
    service = ServiceFactory(
        organization=organization, category=category, duration_minutes=30, price="50.00"
    )
    link = ProfessionalServiceFactory(
        organization=organization,
        professional=professional,
        service=service,
        commission_percentage="25.00",
    )
    weekday = DAY.weekday()
    WorkingHoursFactory(
        organization=organization,
        professional=professional,
        weekday=weekday,
        start_time=time.fromisoformat(work_start or opens),
        end_time=time.fromisoformat(work_end or closes),
    )
    customer = CustomerFactory(organization=organization)
    return organization, membership, professional, category, service, link, customer


def local_start(value, tz="America/Sao_Paulo"):
    return datetime.fromisoformat(value).replace(tzinfo=ZoneInfo(tz))


@pytest.mark.django_db
def test_servico_cruza_meia_noite_no_fuso_da_organizacao():
    organization, membership, professional, _, service, _, customer = setup_schedule(
        opens="23:00", closes="01:00"
    )
    service.duration_minutes = 90
    service.save(update_fields=["duration_minutes"])
    slots = calcular_slots_disponiveis(organization, [service], [professional], DAY)
    slot = next(slot for slot in slots if slot["start_at"].astimezone(organization_tz()).hour == 23)
    assert slot["items"][0]["end_at"].astimezone(organization_tz()).date() == date(2026, 10, 20)
    appointment = create_appointment(
        organization=organization,
        customer=customer,
        items=[{"service": service, "professional": professional, "order": 0}],
        desired_start=slot["start_at"],
        membership=membership,
    )
    assert appointment.items.get().end_at.astimezone(organization_tz()).date() == date(2026, 10, 20)


def organization_tz():
    from zoneinfo import ZoneInfo

    return ZoneInfo("America/Sao_Paulo")


@pytest.mark.django_db
def test_hora_inexistente_na_transicao_de_dst_nao_gera_slot():
    organization = OrganizationFactory(
        timezone="America/New_York", working_hours={"sun": [["01:00", "04:00"]]}
    )
    professional = ProfessionalFactory(organization=organization)
    category = ServiceCategoryFactory(organization=organization)
    service = ServiceFactory(organization=organization, category=category, duration_minutes=30)
    ProfessionalServiceFactory(
        organization=organization, professional=professional, service=service
    )
    WorkingHoursFactory(
        organization=organization,
        professional=professional,
        weekday=6,
        start_time=time(1, 0),
        end_time=time(4, 0),
    )
    slots = calcular_slots_disponiveis(organization, [service], [professional], date(2026, 3, 8))
    local_hours = {slot["start_at"].astimezone(ZoneInfo("America/New_York")).hour for slot in slots}
    assert 2 not in local_hours
    assert 3 in local_hours


@pytest.mark.django_db
def test_servicos_em_profissionais_diferentes_bloqueiam_slot_com_conflito():
    organization, membership, first_pro, category, first_service, _, customer = setup_schedule()
    second_pro = ProfessionalFactory(organization=organization)
    second_service = ServiceFactory(
        organization=organization, category=category, duration_minutes=30
    )
    ProfessionalServiceFactory(
        organization=organization, professional=second_pro, service=second_service
    )
    WorkingHoursFactory(
        organization=organization,
        professional=second_pro,
        weekday=DAY.weekday(),
        start_time=time(9, 0),
        end_time=time(18, 0),
    )
    customer = CustomerFactory(organization=organization)
    appointment = Appointment.objects.create(organization=organization, customer=customer)
    AppointmentItem.objects.create(
        organization=organization,
        appointment=appointment,
        service=second_service,
        professional=second_pro,
        order=0,
        start_at=local_start("2026-10-19T09:30:00").astimezone(UTC),
        end_at=local_start("2026-10-19T10:00:00").astimezone(UTC),
        price=second_service.price,
    )
    slots = calcular_slots_disponiveis(
        organization,
        [first_service, second_service],
        [first_pro, second_pro],
        DAY,
    )
    nine = local_start("2026-10-19T09:00:00").astimezone(UTC)
    assert all(slot["start_at"] != nine for slot in slots)
    with pytest.raises(SlotUnavailable):
        create_appointment(
            organization=organization,
            customer=customer,
            items=[
                {"service": first_service, "professional": first_pro, "order": 0},
                {"service": second_service, "professional": second_pro, "order": 1},
            ],
            desired_start=nine,
            membership=membership,
        )


@pytest.mark.django_db
def test_timeoff_bloqueia_a_disponibilidade():
    organization, membership, professional, _, service, _, customer = setup_schedule()
    TimeOffFactory(
        organization=organization,
        professional=professional,
        start_date=DAY,
        end_date=DAY,
    )
    assert calcular_slots_disponiveis(organization, [service], [professional], DAY) == []
    with pytest.raises(SlotUnavailable):
        create_appointment(
            organization=organization,
            customer=customer,
            items=[{"service": service, "professional": professional, "order": 0}],
            desired_start=local_start("2026-10-19T09:00:00").astimezone(UTC),
            membership=membership,
        )


@pytest.mark.django_db
def test_fora_do_horario_da_organizacao_ou_profissional_nao_tem_slot():
    organization, membership, professional, _, service, _, customer = setup_schedule(
        opens="09:00", closes="18:00", work_start="10:00", work_end="18:00"
    )
    slots = calcular_slots_disponiveis(organization, [service], [professional], DAY)
    nine = local_start("2026-10-19T09:00:00").astimezone(UTC)
    assert all(slot["start_at"] != nine for slot in slots)
    with pytest.raises(SlotUnavailable):
        create_appointment(
            organization=organization,
            customer=customer,
            items=[{"service": service, "professional": professional, "order": 0}],
            desired_start=nine,
            membership=membership,
        )
    organization.working_hours = {"mon": [["10:00", "18:00"]]}
    organization.save(update_fields=["working_hours"])
    with pytest.raises(SlotUnavailable):
        create_appointment(
            organization=organization,
            customer=customer,
            items=[{"service": service, "professional": professional, "order": 0}],
            desired_start=nine,
            membership=membership,
        )
    assert all(
        slot["start_at"].astimezone(organization_tz()).hour >= 10
        for slot in calcular_slots_disponiveis(organization, [service], [professional], DAY)
    )


@pytest.mark.django_db
def test_criacao_revalida_slot_e_grava_preco_e_comissao_snapshot():
    organization, membership, professional, _, service, link, customer = setup_schedule()
    service.buffer_minutes = 15
    service.save(update_fields=["buffer_minutes"])
    start_at = local_start("2026-10-19T09:00:00").astimezone(UTC)
    appointment = create_appointment(
        organization=organization,
        customer=customer,
        items=[{"service": service, "professional": professional, "order": 0}],
        desired_start=start_at,
        membership=membership,
    )
    item = appointment.items.get()
    assert item.price == Decimal(service.price)
    assert item.commission_percentage == Decimal(link.commission_percentage)
    assert item.buffer_minutes == service.buffer_minutes
    service.price = 999
    service.buffer_minutes = 0
    service.save(update_fields=["price"])
    item.refresh_from_db()
    assert item.price != Decimal("999.00")
    assert item.buffer_minutes == 15
    half_past_nine = local_start("2026-10-19T09:30:00").astimezone(UTC)
    later_slots = calcular_slots_disponiveis(organization, [service], [professional], DAY)
    assert all(slot["start_at"] != half_past_nine for slot in later_slots)
    with pytest.raises(SlotUnavailable):
        create_appointment(
            organization=organization,
            customer=customer,
            items=[{"service": service, "professional": professional, "order": 0}],
            desired_start=start_at,
            membership=membership,
        )


@pytest.mark.django_db
def test_api_disponibilidade_cria_e_cancela_agendamento(auth_client, organization):
    professional = ProfessionalFactory(organization=organization, user=organization._owner)
    category = ServiceCategoryFactory(organization=organization)
    service = ServiceFactory(organization=organization, category=category, duration_minutes=30)
    ProfessionalServiceFactory(
        organization=organization, professional=professional, service=service
    )
    WorkingHoursFactory(
        organization=organization,
        professional=professional,
        weekday=DAY.weekday(),
        start_time=time(9, 0),
        end_time=time(18, 0),
    )
    organization.working_hours = {"mon": [["09:00", "18:00"]]}
    organization.save(update_fields=["working_hours"])
    customer = CustomerFactory(organization=organization)
    response = auth_client.get(
        reverse("availability"),
        {"services": str(service.pk), "professional": "any", "date": DAY.isoformat()},
    )
    assert response.status_code == 200
    assert response.json()["slots"]
    start_at = response.json()["slots"][0]["start_at"]
    response = auth_client.post(
        reverse("appointment-list"),
        {
            "customer": customer.pk,
            "start_at": start_at,
            "items": [{"service": service.pk, "professional": professional.pk, "order": 0}],
        },
        format="json",
    )
    assert response.status_code == 201
    appointment_id = response.json()["id"]
    conflict = auth_client.post(
        reverse("appointment-list"),
        {
            "customer": customer.pk,
            "start_at": start_at,
            "items": [{"service": service.pk, "professional": professional.pk, "order": 0}],
        },
        format="json",
    )
    assert conflict.status_code == 409
    assert (
        auth_client.patch(
            reverse("appointment-status", kwargs={"pk": appointment_id}),
            {"status": Appointment.Status.CONFIRMED},
            format="json",
        ).status_code
        == 200
    )
    assert (
        auth_client.post(
            reverse("appointment-cancel", kwargs={"pk": appointment_id}), format="json"
        ).status_code
        == 200
    )


@pytest.mark.django_db
def test_motor_carrega_disponibilidade_em_numero_fixo_de_queries(django_assert_num_queries):
    organization, _, professional, _, service, _, _ = setup_schedule()
    with django_assert_num_queries(4):
        calcular_slots_disponiveis(organization, [service], [professional], DAY)


@pytest.mark.django_db
def test_listagem_de_agendamentos_prefaz_itens_e_relacoes(django_assert_num_queries):
    organization, membership, professional, _, service, _, customer = setup_schedule()
    appointment = Appointment.objects.create(
        organization=organization, customer=customer, created_by=membership
    )
    AppointmentItem.objects.create(
        organization=organization,
        appointment=appointment,
        service=service,
        professional=professional,
        order=0,
        start_at=local_start("2026-10-19T09:00:00").astimezone(UTC),
        end_at=local_start("2026-10-19T09:30:00").astimezone(UTC),
        price=service.price,
    )
    with django_assert_num_queries(2):
        results = list(list_appointments(organization))
        assert len(results) == 1
        assert results[0].items.all()[0].service.name == service.name


@pytest.mark.django_db
def test_professional_so_ve_e_edita_agendamentos_do_proprio_perfil(api_client, organization):
    user = UserFactory()
    MembershipFactory(organization=organization, user=user, role="PROFESSIONAL")
    own_professional = ProfessionalFactory(organization=organization, user=user)
    other_professional = ProfessionalFactory(organization=organization)
    category = ServiceCategoryFactory(organization=organization)
    service = ServiceFactory(organization=organization, category=category)
    customer = CustomerFactory(organization=organization)
    own_appointment = Appointment.objects.create(organization=organization, customer=customer)
    other_appointment = Appointment.objects.create(organization=organization, customer=customer)
    for order, (appointment, professional) in enumerate(
        (
            (own_appointment, own_professional),
            (other_appointment, other_professional),
        )
    ):
        AppointmentItem.objects.create(
            organization=organization,
            appointment=appointment,
            service=service,
            professional=professional,
            order=0,
            start_at=local_start(f"2026-10-19T{9 + order:02}:00:00").astimezone(UTC),
            end_at=local_start(f"2026-10-19T{9 + order:02}:30:00").astimezone(UTC),
            price=service.price,
        )
    api_client.force_authenticate(user=user)
    response = api_client.get(reverse("appointment-list"))
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["results"]] == [own_appointment.pk]
    assert (
        api_client.patch(
            reverse("appointment-status", kwargs={"pk": own_appointment.pk}),
            {"status": Appointment.Status.CONFIRMED},
            format="json",
        ).status_code
        == 200
    )
    assert (
        api_client.get(
            reverse("appointment-detail", kwargs={"pk": other_appointment.pk})
        ).status_code
        == 404
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(
    connection.vendor != "postgresql", reason="Locks concorrentes exigem PostgreSQL."
)
def test_duas_requisicoes_concorrentes_so_criam_um_agendamento():
    organization, membership, professional, _, service, _, customer = setup_schedule()
    start_at = local_start("2026-10-19T09:00:00").astimezone(UTC)
    from threading import Barrier

    barrier = Barrier(2)

    def attempt():
        close_old_connections()
        try:
            from catalog.models import Professional as ProfessionalModel
            from catalog.models import Service as ServiceModel
            from customers.models import Customer as CustomerModel
            from organizations.models import Membership as MembershipModel
            from organizations.models import Organization as OrganizationModel

            org = OrganizationModel.objects.get(pk=organization.pk)
            pro = ProfessionalModel.objects.get(pk=professional.pk)
            svc = ServiceModel.objects.get(pk=service.pk)
            cust = CustomerModel.objects.get(pk=customer.pk)
            member = MembershipModel.objects.get(pk=membership.pk)
            barrier.wait(timeout=5)
            create_appointment(
                organization=org,
                customer=cust,
                items=[{"service": svc, "professional": pro, "order": 0}],
                desired_start=start_at,
                membership=member,
            )
            return "created"
        except SlotUnavailable:
            return "conflict"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: attempt(), range(2)))
    assert sorted(outcomes) == ["conflict", "created"]
    assert Appointment.objects.filter(organization=organization).count() == 1
