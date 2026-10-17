from django.urls import path

from notifications import views

urlpatterns = [
    path("waitlist/", views.WaitlistEntryListCreateView.as_view(), name="waitlist-list-create"),
    path("waitlist/<int:pk>/", views.WaitlistEntryDeleteView.as_view(), name="waitlist-delete"),
    path("public/waitlist/", views.PublicWaitlistEntryCreateView.as_view(), name="public-waitlist"),
]
