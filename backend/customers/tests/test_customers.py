"""Testes de clientes: CRUD, busca, consentimento LGPD e isolamento (IDOR)."""

import pytest
from django.urls import reverse
from rest_framework import status

from customers.factories import CustomerFactory

pytestmark = pytest.mark.django_db


def list_url():
    return reverse("customer-list")


def detail_url(pk):
    return reverse("customer-detail", kwargs={"pk": pk})


def consent_url(pk):
    return reverse("customer-lgpd-consent", kwargs={"pk": pk})


PAYLOAD = {
    "name": "Maria Souza",
    "phone": "+55 11 98888-1234",
    "email": "maria@exemplo.com.br",
    "birthday": "1990-05-10",
}


class TestCriarCliente:
    def test_owner_cria(self, auth_client, organization):
        response = auth_client.post(list_url(), PAYLOAD, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == "Maria Souza"
        assert data["lgpd_consent"] is False

    def test_todo_membro_pode_criar(self, professional_client, organization):
        """Decisão de design: profissional registra o cliente no atendimento."""
        response = professional_client.post(list_url(), PAYLOAD, format="json")
        assert response.status_code == status.HTTP_201_CREATED

    def test_email_normalizado(self, auth_client, organization):
        auth_client.post(list_url(), {**PAYLOAD, "email": "  MARIA@Exemplo.COM.br "}, format="json")
        cliente = organization.customers_customer_set.first()
        assert cliente.email == "maria@exemplo.com.br"

    def test_observacoes_sanitizadas_contra_xss(self, auth_client, organization):
        payload = {**PAYLOAD, "notes": "<script>invasao</script> Prefere manicure."}
        auth_client.post(list_url(), payload, format="json")
        cliente = organization.customers_customer_set.first()
        assert "<script>" not in cliente.notes
        assert "invasao" in cliente.notes
        assert "Prefere manicure." in cliente.notes

    def test_isolamento_tenant_criacao_e_leitura(
        self, auth_client, organization, other_organization
    ):
        ClienteB = CustomerFactory(organization=other_organization)
        response = auth_client.get(detail_url(ClienteB.pk))
        assert response.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)


class TestListarClientes:
    def test_busca_por_nome_telefone_email(self, auth_client, organization):
        alvo = CustomerFactory(
            organization=organization, name="Clara Nunes", phone="+5511990001111"
        )
        outro = CustomerFactory(organization=organization, name="Outro", phone="+5511880002222")
        CustomerFactory(organization=organization, email="clara.nunes@exemplo.com.br")

        resposta_nome = auth_client.get(list_url(), {"search": "clara"})
        assert resposta_nome.json()["count"] == 2
        ids = {item["id"] for item in resposta_nome.json()["results"]}
        assert alvo.pk in ids

        resposta_telefone = auth_client.get(list_url(), {"search": "99000"})
        assert resposta_telefone.json()["count"] == 1
        assert resposta_telefone.json()["results"][0]["id"] == alvo.pk

        resposta_email = auth_client.get(list_url(), {"search": "outro"})
        assert resposta_email.json()["count"] == 1
        assert resposta_email.json()["results"][0]["id"] == outro.pk

    def test_isolamento_tenant_nao_ve_clientes_de_outro(
        self, auth_client, organization, other_organization
    ):
        CustomerFactory(organization=other_organization)
        assert auth_client.get(list_url()).json()["count"] == 0

    def test_paginacao(self, auth_client, organization):
        for _ in range(25):
            CustomerFactory(organization=organization)
        data = auth_client.get(list_url()).json()
        assert data["count"] == 25
        assert len(data["results"]) == 20

    def test_sem_n_plus_1_na_listagem(self, auth_client, organization, django_assert_num_queries):
        for _ in range(5):
            CustomerFactory(organization=organization)
        # membership do tenant + COUNT + página
        with django_assert_num_queries(3):
            response = auth_client.get(list_url())
        assert response.status_code == status.HTTP_200_OK


class TestEditarExcluirCliente:
    def test_owner_patch(self, auth_client, organization):
        cliente = CustomerFactory(organization=organization)
        response = auth_client.patch(detail_url(cliente.pk), {"email": "novo@x.com"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        cliente.refresh_from_db()
        assert cliente.email == "novo@x.com"

    def test_idor_patch_de_outro_tenant(
        self, professional, other_organization, professional_client
    ):
        cliente_b = CustomerFactory(organization=other_organization)
        response = professional_client.patch(
            detail_url(cliente_b.pk), {"phone": "x"}, format="json"
        )
        assert response.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)
        cliente_b.refresh_from_db()
        assert cliente_b.phone != "x"

    def test_excluir(self, auth_client, organization):
        cliente = CustomerFactory(organization=organization)
        assert auth_client.delete(detail_url(cliente.pk)).status_code == status.HTTP_204_NO_CONTENT


class TestConsentimentoLGPD:
    def test_consentir_grava_carimbo(self, auth_client, organization):
        cliente = CustomerFactory(
            organization=organization, lgpd_consent=False, lgpd_consent_at=None
        )
        response = auth_client.post(consent_url(cliente.pk), {"consented": True}, format="json")
        assert response.status_code == status.HTTP_200_OK
        cliente.refresh_from_db()
        assert cliente.lgpd_consent is True
        assert cliente.lgpd_consent_at is not None

    def test_revogar_apaga_carimbo(self, auth_client, organization):
        cliente = CustomerFactory(organization=organization)
        response = auth_client.post(consent_url(cliente.pk), {"consented": False}, format="json")
        assert response.status_code == status.HTTP_200_OK
        cliente.refresh_from_db()
        assert cliente.lgpd_consent is False
        assert cliente.lgpd_consent_at is None

    def test_payload_invalido_rejeitado(self, auth_client, organization):
        cliente = CustomerFactory(organization=organization)
        response = auth_client.post(consent_url(cliente.pk), {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_idor_consentimento_outro_tenant(
        self, professional, other_organization, professional_client
    ):
        cliente_b = CustomerFactory(organization=other_organization)
        response = professional_client.post(
            consent_url(cliente_b.pk), {"consented": True}, format="json"
        )
        assert response.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)
        cliente_b.refresh_from_db()
        assert cliente_b.lgpd_consent is False

    def test_professional_pode_consentir_cliente_do_salao(self, professional_client, organization):
        cliente = CustomerFactory(organization=organization)
        response = professional_client.post(
            consent_url(cliente.pk), {"consented": True}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
