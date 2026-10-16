from django.urls import path

from catalog import views

urlpatterns = [
    path(
        "service-categories/",
        views.ServiceCategoryListCreateView.as_view(),
        name="service-category-list",
    ),
    path(
        "service-categories/<int:pk>/",
        views.ServiceCategoryDetailView.as_view(),
        name="service-category-detail",
    ),
    path("services/", views.ServiceListCreateView.as_view(), name="service-list"),
    path("services/<int:pk>/", views.ServiceDetailView.as_view(), name="service-detail"),
    path(
        "professionals/",
        views.ProfessionalListCreateView.as_view(),
        name="professional-list",
    ),
    path(
        "professionals/<int:pk>/",
        views.ProfessionalDetailView.as_view(),
        name="professional-detail",
    ),
    path(
        "professionals/<int:professional_id>/services/",
        views.ProfessionalServiceListCreateView.as_view(),
        name="professional-service-list",
    ),
    path(
        "professional-services/<int:pk>/",
        views.ProfessionalServiceDetailView.as_view(),
        name="professional-service-detail",
    ),
    path(
        "professionals/<int:professional_id>/working-hours/",
        views.WorkingHoursListCreateView.as_view(),
        name="professional-working-hours-list",
    ),
    path(
        "working-hours/<int:pk>/",
        views.WorkingHoursDetailView.as_view(),
        name="professional-working-hours-detail",
    ),
    path(
        "professionals/<int:professional_id>/time-offs/",
        views.TimeOffListCreateView.as_view(),
        name="professional-timeoff-list",
    ),
    path(
        "time-offs/<int:pk>/",
        views.TimeOffDetailView.as_view(),
        name="professional-timeoff-detail",
    ),
]
