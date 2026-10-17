"""
Testes de WorkingHours e TimeOff: CRUD aninhado, validações e a regra explícita
da Fase 2 — PROFESSIONAL mexe apenas nos PRÓPRIOS registros (403 do contrário).
"""

import datetime

import pytest
from django.urls import reverse
from rest_framework import status

from catalog.factories import ProfessionalFactory, TimeOffFactory, WorkingHoursFactory
from catalog.models import TimeOff

pytestmark = pytest.mark.django_db


def wh_list_url(professional_pk):
    return reverse("professional-working-hours-list", kwargs={"professional_id": professional_pk})


def wh_detail_url(pk):
    return reverse("professional-working-hours-detail", kwargs={"pk": pk})


def to_list_url(professional_pk):
    return reverse("professional-timeoff-list", kwargs={"professional_id": professional_pk})


def to_detail_url(pk):
    return reverse("professional-timeoff-detail", kwargs={"pk": pk})


JANELA = {"weekday": 1, "start_time": "09:00", "end_time": "18:00"}
FOLGA = {"start_date": "2026-12-20", "end_date": "2026-12-25", "reason": "Férias"}


@pytest.fixture
def colega(organization):
    """Outro profissional DO MESMO salão, sem agenda própria."""
    return ProfessionalFactory(organization=organization, name="Colega do salão")


class TestWorkingHours:
    def test_owner_cria_janela(self, auth_client, professional):
        response = auth_client.post(wh_list_url(professional.pk), JANELA, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert professional.working_hours.count() == 1

    def test_horario_invalido_rejeitado(self, auth_client, professional):
        payload = {**JANELA, "start_time": "18:00", "end_time": "18:00"}
        response = auth_client.post(wh_list_url(professional.pk), payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert professional.working_hours.count() == 0

    def test_horario_noturno_que_cruza_meia_noite_e_permitido(self, auth_client, professional):
        response = auth_client.post(
            wh_list_url(professional.pk),
            {**JANELA, "start_time": "22:00", "end_time": "02:00"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_professional_cria_no_proprio(self, professional_client, professional):
        response = professional_client.post(wh_list_url(professional.pk), JANELA, format="json")
        assert response.status_code == status.HTTP_201_CREATED

    def test_professional_403_na_agenda_do_outro_mesmo_salao(
        self, professional, organization, professional_client, colega
    ):
        """
        Caso explícito do enunciado: um PROFESSIONAL tentando mexer na agenda
        de OUTRO profissional do MESMO salão recebe 403.
        """
        response = professional_client.post(wh_list_url(colega.pk), JANELA, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert colega.working_hours.count() == 0

    def test_professional_403_no_patch_do_outro(
        self, professional, organization, professional_client, colega
    ):
        janela_colega = WorkingHoursFactory(
            organization=organization, professional=colega, weekday=3
        )
        response = professional_client.patch(
            wh_detail_url(janela_colega.pk), {"start_time": "06:00"}, format="json"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        janela_colega.refresh_from_db()
        assert janela_colega.start_time == datetime.time(9, 0)

    def test_professional_edita_a_proprio(self, professional_client, professional):
        janela = WorkingHoursFactory(
            organization=professional.organization, professional=professional
        )
        response = professional_client.patch(
            wh_detail_url(janela.pk), {"end_time": "22:00"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        janela.refresh_from_db()
        assert janela.end_time == datetime.time(22, 0)

    def test_idor_de_outro_tenant_404(self, professional, other_organization, professional_client):
        janela_b = WorkingHoursFactory(
            organization=other_organization, professional=other_organization._professional
        )
        response = professional_client.get(wh_list_url(janela_b.professional.pk))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_isolamento_patch_cross_tenant_403(
        self, professional, other_organization, professional_client
    ):
        """Defesa em profundidade: objeto de outro tenant nunca é editável."""
        janela_b = WorkingHoursFactory(
            organization=other_organization, professional=other_organization._professional
        )
        response = professional_client.patch(
            wh_detail_url(janela_b.pk), {"start_time": "05:00"}, format="json"
        )
        # 404 (escopo de tenant) OU 403 (defesa em profundidade de objeto):
        assert response.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_multiplos_intervalos_no_mesmo_dia_permitem_pausa_de_almoco(
        self, auth_client, professional
    ):
        auth_client.post(
            wh_list_url(professional.pk),
            {**JANELA, "start_time": "09:00", "end_time": "12:00"},
            format="json",
        )
        response = auth_client.post(
            wh_list_url(professional.pk),
            {**JANELA, "start_time": "13:00", "end_time": "18:00"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert professional.working_hours.count() == 2


class TestTimeOff:
    def test_owner_cria_folga(self, auth_client, professional):
        response = auth_client.post(to_list_url(professional.pk), FOLGA, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert professional.time_offs.count() == 1

    def test_folga_invalida_rejeitada(self, auth_client, professional):
        payload = {**FOLGA, "start_date": "2026-12-26", "end_date": "2026-12-25"}
        response = auth_client.post(to_list_url(professional.pk), payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_reason_sanitizado(self, auth_client, professional):
        payload = {**FOLGA, "reason": "<script>virus</script>Férias!"}
        auth_client.post(to_list_url(professional.pk), payload, format="json")
        folga = professional.time_offs.first()
        assert "<script>" not in folga.reason

    def test_professional_cria_no_proprio(self, professional_client, professional):
        response = professional_client.post(to_list_url(professional.pk), FOLGA, format="json")
        assert response.status_code == status.HTTP_201_CREATED

    def test_professional_403_na_folga_do_outro(
        self, professional, organization, professional_client, colega
    ):
        response = professional_client.post(to_list_url(colega.pk), FOLGA, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert colega.time_offs.count() == 0

    def test_professional_403_no_delete_do_outro(
        self, professional, organization, professional_client, colega
    ):
        folga_colega = TimeOffFactory(organization=organization, professional=colega)
        response = professional_client.delete(to_detail_url(folga_colega.pk))
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert TimeOff.objects.filter(pk=folga_colega.pk).exists()

    def test_owner_lista_folgas_do_profissional(self, auth_client, professional):
        TimeOffFactory(organization=professional.organization, professional=professional)
        response = auth_client.get(to_list_url(professional.pk))
        assert response.json()["count"] == 1
