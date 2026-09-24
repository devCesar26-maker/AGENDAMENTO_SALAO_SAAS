"""
JWT adaptado ao multi-tenant: claims de organização no access token e views de
obtenção/refresh que também sabem setar cookies httpOnly (contas em accounts).
"""

from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView


class TenantTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Login por e-mail; embute organização ativa e role no access token."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["email"] = user.email
        membership = user.memberships.select_related("organization").order_by("created_at").first()
        if membership:
            token["org_id"] = str(membership.organization_id)
            token["org_slug"] = membership.organization.slug
            token["org_role"] = membership.role
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        membership = self.user.memberships.order_by("created_at").first()
        data["user"] = {
            "id": self.user.id,
            "email": self.user.email,
            "first_name": self.user.first_name,
            "last_name": self.user.last_name,
            "organization": (
                {"id": membership.organization_id, "slug": membership.organization.slug}
                if membership
                else None
            ),
            "role": membership.role if membership else None,
        }
        return data


class TenantTokenObtainPairView(TokenObtainPairView):
    serializer_class = TenantTokenObtainPairSerializer
