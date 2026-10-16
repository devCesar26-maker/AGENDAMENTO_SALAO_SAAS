from django.urls import path

from customers import views

urlpatterns = [
    path("customers/", views.CustomerListCreateView.as_view(), name="customer-list"),
    path("customers/<int:pk>/", views.CustomerDetailView.as_view(), name="customer-detail"),
    path(
        "customers/<int:pk>/lgpd-consent/",
        views.CustomerLgpdConsentView.as_view(),
        name="customer-lgpd-consent",
    ),
]
