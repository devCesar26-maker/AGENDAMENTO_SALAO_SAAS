from django.urls import path

from customers import views

urlpatterns = [
    path("customers/", views.CustomerListCreateView.as_view(), name="customer-list"),
    path(
        "customers/<int:pk>/",
        views.CustomerDetailView.as_view(),
        name="customer-detail",
    ),
    path(
        "customers/<int:pk>/lgpd-consent/",
        views.CustomerLgpdConsentView.as_view(),
        name="customer-lgpd-consent",
    ),
    path("customers/<int:pk>/export/", views.CustomerExportView.as_view(), name="customer-export"),
    path("customers/<int:pk>/anonymize/", views.CustomerAnonymizeView.as_view(), name="customer-anonymize"),
]
