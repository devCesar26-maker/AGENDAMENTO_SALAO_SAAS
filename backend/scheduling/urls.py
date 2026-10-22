from django.urls import path

from scheduling import public, views

urlpatterns = [
    path("public/catalog/", public.PublicCatalogView.as_view(), name="public-catalog"),
    path(
        "public/professionals/",
        public.PublicProfessionalsView.as_view(),
        name="public-professionals",
    ),
    path(
        "public/availability/",
        public.PublicAvailabilityView.as_view(),
        name="public-availability",
    ),
    path(
        "public/appointments/",
        public.PublicAppointmentCreateView.as_view(),
        name="public-appointment-create",
    ),
    path(
        "public/appointments/tokens/<str:token>/",
        public.PublicAppointmentMagicLinkView.as_view(),
        name="public-appointment-magic-link",
    ),
    path(
        "public/appointments/tokens/<str:token>/cancel/",
        public.PublicAppointmentMagicLinkCancelView.as_view(),
        name="public-appointment-magic-link-cancel",
    ),
    path(
        "public/ratings/<str:token>/",
        public.PublicRatingView.as_view(),
        name="public-rating",
    ),
    path(
        "public/suggestions/<str:token>/",
        public.PublicRecurringSuggestionView.as_view(),
        name="public-suggestion",
    ),
    path(
        "public/suggestions/<str:token>/<str:decision>/",
        public.PublicRecurringSuggestionView.as_view(),
        name="public-suggestion-decision",
    ),
    path("availability/", views.AvailabilityView.as_view(), name="availability"),
    path(
        "appointments/",
        views.AppointmentListCreateView.as_view(),
        name="appointment-list",
    ),
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
        "appointments/<int:pk>/reschedule/",
        views.AppointmentRescheduleView.as_view(),
        name="appointment-reschedule",
    ),
    path(
        "appointments/<int:pk>/cancel/",
        views.AppointmentCancelView.as_view(),
        name="appointment-cancel",
    ),
]
