from django.urls import path

from accounts import serializers, views

urlpatterns = [
    # Auth (públicas; ROTATED_REFRESH etc. conforme SIMPLE_JWT em settings):
    path("auth/register/", views.RegisterView.as_view(), name="auth-register"),
    path(
        "auth/login/",
        views.LoginView.as_view(serializer_class=serializers.LoginSerializer),
        name="auth-login",
    ),
    path("auth/refresh/", views.RefreshTokenView.as_view(), name="auth-refresh"),
    path("auth/logout/", views.LogoutView.as_view(), name="auth-logout"),
    path(
        "auth/password/reset/",
        views.PasswordResetRequestView.as_view(),
        name="auth-password-reset",
    ),
    path(
        "auth/password/reset/confirm/",
        views.PasswordResetConfirmView.as_view(),
        name="auth-password-reset-confirm",
    ),
    path("me/", views.MeView.as_view(), name="me"),
]
