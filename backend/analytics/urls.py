from django.urls import path

from analytics import views

urlpatterns = [
    path("metrics/overview/", views.MetricsOverviewView.as_view(), name="metrics-overview"),
    path("metrics/services/", views.MetricsServicesView.as_view(), name="metrics-services"),
    path(
        "metrics/professionals/",
        views.MetricsProfessionalsView.as_view(),
        name="metrics-professionals",
    ),
    path(
        "exports/appointments/", views.AppointmentsExportView.as_view(), name="export-appointments"
    ),
    path("exports/customers/", views.CustomersExportView.as_view(), name="export-customers"),
    path("exports/commissions/", views.CommissionsExportView.as_view(), name="export-commissions"),
    path("audit-log/", views.AuditLogListView.as_view(), name="audit-log-list"),
]
