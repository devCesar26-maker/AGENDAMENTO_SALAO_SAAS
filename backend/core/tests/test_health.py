from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase


class HealthEndpointTest(APITestCase):
    def test_health_publico_responde_200(self):
        response = APIClient().get(reverse("health"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["status"], "ok")
