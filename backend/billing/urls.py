from django.urls import path

from billing.views import (
    CheckoutView,
    MercadoPagoCallbackView,
    MercadoPagoConnectView,
    MercadoPagoWebhookView,
    PlansView,
    UsageView,
)

urlpatterns = [
    path("billing/plans/", PlansView.as_view(), name="billing-plans"),
    path("billing/usage/", UsageView.as_view(), name="billing-usage"),
    path("billing/checkout/", CheckoutView.as_view(), name="billing-checkout"),
    path(
        "billing/mercadopago/connect/",
        MercadoPagoConnectView.as_view(),
        name="billing-mercadopago-connect",
    ),
    path(
        "billing/mercadopago/callback/",
        MercadoPagoCallbackView.as_view(),
        name="billing-mercadopago-callback",
    ),
    path(
        "billing/webhook/mercadopago/",
        MercadoPagoWebhookView.as_view(),
        name="billing-mercadopago-webhook",
    ),
]
