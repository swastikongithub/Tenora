from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.models import Membership
from apps.tenants.permissions import IsTenantMember, IsTenantOwner
from apps.tenants.serializers import (
    MembershipCreateSerializer,
    MembershipSerializer,
    TenantCreateSerializer,
    TenantSerializer,
)
from apps.tenants.services import (
    AlreadyAMember,
    MembershipService,
    SlugAlreadyTaken,
    TenantService,
    UserNotFound,
)


class TenantCreateView(APIView):
    """POST /api/tenants/ — global path, authenticated, no tenant context."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = TenantCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            tenant, membership = TenantService.create_tenant(
                user=request.user,
                name=serializer.validated_data["name"],
                slug=serializer.validated_data["slug"],
            )
        except SlugAlreadyTaken:
            return Response(
                {"slug": ["A tenant with this slug already exists."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        body = TenantSerializer(tenant).data
        body["role"] = membership.role
        return Response(body, status=status.HTTP_201_CREATED)


class MyTenantsView(APIView):
    """GET /api/tenants/me/ — every tenant the caller belongs to, with role."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        memberships = TenantService.tenants_for_user(request.user)
        body = [
            {**TenantSerializer(m.tenant).data, "role": m.role} for m in memberships
        ]
        return Response(body, status=status.HTTP_200_OK)


class MembershipListCreateView(APIView):
    """
    GET  /api/memberships/ — list the current tenant's members (OWNER or MEMBER).
    POST /api/memberships/ — add an existing user as MEMBER (OWNER only).

    Tenant-scoped: request.tenant / request.membership are resolved by
    TenantJWTAuthentication before this view runs.
    """

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsTenantOwner()]
        return [IsAuthenticated(), IsTenantMember()]

    def get(self, request):
        # Scoped manager — the sanctioned mechanism, never .filter(tenant=).
        qs = Membership.objects.for_tenant(request.tenant).select_related("user")
        return Response(
            MembershipSerializer(qs, many=True).data, status=status.HTTP_200_OK
        )

    def post(self, request):
        serializer = MembershipCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            membership = MembershipService.add_member(
                tenant=request.tenant, email=serializer.validated_data["email"]
            )
        except UserNotFound:
            return Response(
                {"detail": "No user with this email exists."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except AlreadyAMember:
            return Response(
                {"email": ["This user is already a member of this tenant."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            MembershipSerializer(membership).data, status=status.HTTP_201_CREATED
        )
