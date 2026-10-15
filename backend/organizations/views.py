"""
Endpoints de salões, membros e convites (views finas; regras em services.py).
"""

from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api.pagination import DefaultPagination
from organizations import selectors, services
from organizations.models import Invitation, Membership
from organizations.permissions import (
    IsOrganizationManagerOrOwner,
    IsOrganizationMember,
    IsOrganizationOwner,
)
from organizations.serializers import (
    InvitationAcceptSerializer,
    InvitationCreateSerializer,
    InvitationSerializer,
    MemberSerializer,
    OrganizationSerializer,
)


class OrganizationSlugMixin:
    """Resolve o salão pelo slug da URL (cached para não duplicar queries)."""

    def get_organization(self):
        organization = getattr(self, "_organization", None)
        if organization is None:
            self._organization = selectors.get_organization_by_slug(self.kwargs["slug"])
        if self._organization is None:
            from django.http import Http404

            raise Http404
        return self._organization


class OrganizationDetailView(OrganizationSlugMixin, generics.RetrieveUpdateAPIView):
    """GET (membro) / PATCH (OWNER|MANAGER) dos dados do salão."""

    serializer_class = OrganizationSerializer

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [IsOrganizationManagerOrOwner()]
        return [IsOrganizationMember()]

    def get_object(self):
        return self.get_organization()


class InvitationListCreateView(OrganizationSlugMixin, generics.ListCreateAPIView):
    """POST/GET de convites — apenas OWNER/MANAGER. Pendentes e não expirados."""

    permission_classes = [IsOrganizationManagerOrOwner]
    pagination_class = DefaultPagination
    # Stub para o gerador de schema (o queryset real vem de get_queryset()).
    queryset = Invitation.objects.none()

    def get_serializer_class(self):
        if self.request.method == "POST":
            return InvitationCreateSerializer
        return InvitationSerializer

    def get_queryset(self):
        return selectors.list_pending_invitations(self.get_organization())

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation = services.create_invitation(
            organization=self.get_organization(),
            email=serializer.validated_data["email"],
            role=serializer.validated_data["role"],
            invited_by=request.user,
        )
        return Response(
            InvitationSerializer(invitation, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )


class InvitationAcceptView(APIView):
    """
    POST público: aceita convite por token. Cria o User (com senha) se o
    e-mail ainda não existe; o role vem SEMPRE do Invitation, nunca do body.
    """

    authentication_classes: list = []
    permission_classes: list = []

    @extend_schema(
        request=InvitationAcceptSerializer,
        responses={201: dict},
        summary="Aceita convite por token; role vem do Invitation, nunca do payload",
        tags=["organizations"],
    )
    def post(self, request, token: str):
        serializer = InvitationAcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = services.accept_invitation(
            token=token,
            password=serializer.validated_data.get("password"),
            first_name=serializer.validated_data.get("first_name", ""),
            last_name=serializer.validated_data.get("last_name", ""),
        )
        return Response(self._payload(membership), status=status.HTTP_201_CREATED)

    def _payload(self, membership: Membership) -> dict:
        from core.api.jwt import TenantTokenObtainPairSerializer

        tokens = TenantTokenObtainPairSerializer.get_token(membership.user)
        return {
            "access": str(tokens.access_token),
            "refresh": str(tokens),
            "organization": {
                "id": membership.organization_id,
                "name": membership.organization.name,
                "slug": membership.organization.slug,
            },
            "role": membership.role,
        }


class MemberListView(OrganizationSlugMixin, generics.ListAPIView):
    """Lista de membros (qualquer membro autenticado). Sem N+1 (select_related)."""

    serializer_class = MemberSerializer
    permission_classes = [IsOrganizationMember]
    pagination_class = DefaultPagination
    # Stub para o gerador de schema (o queryset real vem de get_queryset()).
    queryset = Membership.objects.none()

    def get_queryset(self):
        return selectors.list_members(self.get_organization())


class MemberDetailView(OrganizationSlugMixin, generics.RetrieveUpdateAPIView):
    """GET (membro) / PATCH — role e status, restrito ao OWNER."""

    serializer_class = MemberSerializer

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [IsOrganizationOwner()]
        return [IsOrganizationMember()]

    def get_queryset(self):
        return selectors.list_members(self.get_organization())

    def perform_update(self, serializer):
        services.update_member(
            self.get_object(),
            role=serializer.validated_data.get("role"),
            is_active=serializer.validated_data.get("is_active"),
        )
