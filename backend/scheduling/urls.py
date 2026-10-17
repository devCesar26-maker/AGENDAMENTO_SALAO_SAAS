from django.urls import path

from scheduling import views

urlpatterns = [
    path("availability/", views.AvailabilityView.as_view(), name="availability"),
    path("appointments/", views.AppointmentListCreateView.as_view(), name="appointment-list"),
    path(
        "appointments/<int:pk>/",
        views.AppointmentDetailView.as_view(),
        name="appointment-detail",
    ),
    path(
        "appointments/<int:pk>/status/",
        views.AppointmentStatusView.as_view(),
        name="appointment-status",
    ),
    path(
        "appointments/<int:pk>/cancel/",
        views.AppointmentCancelView.as_view(),
        name="appointment-cancel",
    ),
]
