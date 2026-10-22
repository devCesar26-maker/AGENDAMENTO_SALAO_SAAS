from django.urls import path

from organizations import views

urlpatterns = [
    path(
        "organizations/<slug:slug>/",
        views.OrganizationDetailView.as_view(),
        name="organization-detail",
    ),
    path(
        "organizations/<slug:slug>/invitations/",
        views.InvitationListCreateView.as_view(),
        name="organization-invitations",
    ),
    path(
        "organizations/<slug:slug>/invitations/<int:pk>/",
        views.InvitationDetailView.as_view(),
        name="organization-invitation-detail",
    ),
    path(
        "organizations/<slug:slug>/webhooks/",
        views.WebhookListCreateView.as_view(),
        name="organization-webhooks",
    ),
    path(
        "organizations/<slug:slug>/webhooks/<int:pk>/",
        views.WebhookDetailView.as_view(),
        name="organization-webhook-detail",
    ),
    path(
        "organizations/<slug:slug>/members/",
        views.MemberListView.as_view(),
        name="organization-members",
    ),
    path(
        "organizations/<slug:slug>/members/<int:pk>/",
        views.MemberDetailView.as_view(),
        name="organization-member-detail",
    ),
    path(
        "invitations/<str:token>/accept/",
        views.InvitationAcceptView.as_view(),
        name="invitation-accept",
    ),
]
