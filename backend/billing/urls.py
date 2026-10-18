from django.urls import path

from billing.views import CheckoutView, MercadoPagoWebhookView, PlansView, UsageView

urlpatterns = [
    path("billing/plans/", PlansView.as_view(), name="billing-plans"),
    path("billing/usage/", UsageView.as_view(), name="billing-usage"),
    path("billing/checkout/", CheckoutView.as_view(), name="billing-checkout"),
    path(
        "billing/webhook/mercadopago/",
        MercadoPagoWebhookView.as_view(),
        name="billing-mercadopago-webhook",
    ),
]
