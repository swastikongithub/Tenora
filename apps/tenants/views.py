from django.http import Http404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.properties.models import Unit
from apps.tenants.limits import MemberLimitReached, PlanLimitService, WorkspaceLimitReached
from apps.tenants.models import Invitation, Membership
from apps.tenants.permissions import IsTenantMember, IsTenantOwner, RequiresCapability
from apps.tenants.serializers import (
    InvitationCreateSerializer,
    InvitationRespondSerializer,
    InvitationSerializer,
    MembershipCreateSerializer,
    MembershipSerializer,
    TenantCreateSerializer,
    TenantSerializer,
)
from apps.tenants.services import (
    AlreadyAMember,
    InvalidOwnershipTransfer,
    InvitationAlreadyPending,
    InvitationNotFound,
    InvitationNotPending,
    InvitationService,
    LastOwnerCannotLeave,
    MembershipNotRemovable,
    MembershipService,
    SlugAlreadyTaken,
    TenantService,
    UserNotFound,
    WorkspaceNotEmpty,
    WorkspaceUnavailable,
)


def _member_limit_response(exc):
    return Response(
        {
            "detail": (
                f"This workspace has reached its plan's member limit ({exc.used}/{exc.limit}). "
                "Pending invitations reserve a seat. Upgrade the plan or free a seat first."
            ),
            "code": "member_limit_reached",
            "used": exc.used,
            "limit": exc.limit,
        },
        status=status.HTTP_403_FORBIDDEN,
    )


def _workspace_limit_response(exc):
    return Response(
        {
            "detail": (
                f"Your plan allows {exc.limit} workspace(s) and you own {exc.used}. "
                "Upgrade your plan to create another."
            ),
            "code": "workspace_limit_reached",
            "used": exc.used,
            "limit": exc.limit,
        },
        status=status.HTTP_403_FORBIDDEN,
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
        except WorkspaceLimitReached as exc:
            return _workspace_limit_response(exc)

        body = TenantSerializer(tenant).data
        body["role"] = membership.role
        return Response(body, status=status.HTTP_201_CREATED)


class MyTenantsView(APIView):
    """GET /api/tenants/me/ — every tenant the caller actively belongs to, with role."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        memberships = TenantService.tenants_for_user(request.user)
        body = [
            {**TenantSerializer(m.tenant).data, "role": m.role} for m in memberships
        ]
        return Response(body, status=status.HTTP_200_OK)


def _create_invitation(request, data):
    unit = None
    if data.get("unit_id"):
        unit = (
            Unit.objects.for_tenant(request.tenant)
            .select_related("property")
            .filter(pk=data["unit_id"])
            .first()
        )
        if unit is None:
            return None, Response(
                {"unit_id": ["Unit not found."]}, status=status.HTTP_400_BAD_REQUEST
            )
    try:
        invitation = InvitationService.create(
            tenant=request.tenant,
            inviter=request.user,
            email=data["email"],
            unit=unit,
            message=data.get("message", ""),
        )
    except UserNotFound:
        return None, Response(
            {"detail": "No user with this email exists."},
            status=status.HTTP_404_NOT_FOUND,
        )
    except AlreadyAMember:
        return None, Response(
            {"email": ["This user is already a member of this tenant."]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except InvitationAlreadyPending:
        return None, Response(
            {"email": ["This user already has a pending invitation."]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except MemberLimitReached as exc:
        return None, _member_limit_response(exc)
    except WorkspaceUnavailable:
        return None, Response(
            {"detail": "This workspace cannot accept new members."},
            status=status.HTTP_409_CONFLICT,
        )
    return invitation, None


class MembershipListCreateView(APIView):
    """
    GET  /api/memberships/ — list the current tenant's ACTIVE members.
    POST /api/memberships/ — invite an existing user (OWNER only).

    Property-billing plan §4.4: POST no longer creates a membership. It creates
    a PENDING invitation that only the invited user can accept, so an owner can
    never silently add someone's account to their workspace. The response is
    the invitation (201).

    Tenant-scoped: request.tenant / request.membership are resolved by
    TenantJWTAuthentication before this view runs.
    """

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsTenantOwner()]
        return [IsAuthenticated(), IsTenantMember()]

    def get(self, request):
        # Scoped manager — the sanctioned mechanism, never .filter(tenant=).
        qs = (
            Membership.objects.for_tenant(request.tenant)
            .filter(status=Membership.Status.ACTIVE)
            .select_related("user")
        )
        return Response(
            MembershipSerializer(qs, many=True).data, status=status.HTTP_200_OK
        )

    def post(self, request):
        serializer = MembershipCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation, error = _create_invitation(request, serializer.validated_data)
        if error is not None:
            return error
        return Response(
            InvitationSerializer(invitation).data, status=status.HTTP_201_CREATED
        )


class InvitationListCreateView(APIView):
    """GET/POST /api/invitations/ — the workspace's invitations (OWNER)."""

    permission_classes = [IsAuthenticated, IsTenantMember, RequiresCapability("members.manage")]

    def get(self, request):
        qs = InvitationService.for_tenant(request.tenant)
        status_param = request.query_params.get("status")
        if status_param in Invitation.Status.values:
            qs = qs.filter(status=status_param)
        return Response(InvitationSerializer(qs, many=True).data)

    def post(self, request):
        serializer = InvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation, error = _create_invitation(request, serializer.validated_data)
        if error is not None:
            return error
        return Response(InvitationSerializer(invitation).data, status=status.HTTP_201_CREATED)


class InvitationCancelView(APIView):
    permission_classes = [IsAuthenticated, IsTenantMember, RequiresCapability("members.manage")]

    def post(self, request, pk):
        try:
            invitation = InvitationService.cancel(
                actor=request.user, tenant=request.tenant, invitation_id=pk
            )
        except InvitationNotFound:
            raise Http404
        except InvitationNotPending as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(InvitationSerializer(invitation).data)


class MyInvitationsView(APIView):
    """GET /api/invitations/mine/ — invitations addressed to the caller (global path)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = InvitationService.for_user(request.user)
        if request.query_params.get("status") in Invitation.Status.values:
            qs = qs.filter(status=request.query_params["status"])
        return Response(InvitationSerializer(qs, many=True).data)


class InvitationRespondView(APIView):
    """POST /api/invitations/respond/ — {id, action: accept|decline} (global path).
    The invitation must be addressed to the authenticated user; anyone else's id
    is a 404."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = InvitationRespondSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            invitation = InvitationService.respond(
                user=request.user,
                invitation_id=serializer.validated_data["id"],
                accept=serializer.validated_data["action"] == "accept",
            )
        except InvitationNotFound:
            return Response({"detail": "Invitation not found."}, status=status.HTTP_404_NOT_FOUND)
        except InvitationNotPending as exc:
            return Response({"detail": str(exc), "code": "invitation_not_pending"}, status=status.HTTP_409_CONFLICT)
        except MemberLimitReached as exc:
            return _member_limit_response(exc)
        except WorkspaceUnavailable:
            return Response(
                {"detail": "This workspace is no longer accepting members."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(InvitationSerializer(invitation).data)


class LeaveWorkspaceView(APIView):
    """POST /api/memberships/leave/ — the caller leaves the X-Tenant-ID workspace."""

    permission_classes = [IsAuthenticated, IsTenantMember]

    def post(self, request):
        try:
            MembershipService.leave(user=request.user, tenant=request.tenant)
        except LastOwnerCannotLeave:
            return Response(
                {
                    "detail": (
                        "You are this workspace's only owner. Transfer ownership to a "
                        "resident, or close the workspace, before leaving."
                    ),
                    "code": "last_owner",
                },
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_200_OK)


class MembershipRemoveView(APIView):
    permission_classes = [IsAuthenticated, IsTenantMember, RequiresCapability("members.manage")]

    def post(self, request, pk):
        membership = Membership.objects.for_tenant(request.tenant).filter(pk=pk).first()
        if membership is None:
            raise Http404
        try:
            membership = MembershipService.remove(
                actor=request.user, tenant=request.tenant, membership=membership
            )
        except MembershipNotRemovable:
            return Response(
                {"detail": "Only resident memberships can be removed."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(MembershipSerializer(membership).data)


class OwnershipTransferView(APIView):
    permission_classes = [IsAuthenticated, IsTenantMember, RequiresCapability("workspace.manage")]

    def post(self, request, pk):
        target = Membership.objects.for_tenant(request.tenant).filter(pk=pk).first()
        if target is None:
            raise Http404
        try:
            target = MembershipService.transfer_ownership(
                actor=request.user, tenant=request.tenant, target=target
            )
        except InvalidOwnershipTransfer:
            return Response(
                {"detail": "Ownership can only be transferred to an active resident member."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except WorkspaceLimitReached:
            return Response(
                {
                    "detail": "That person's plan does not allow them to own another workspace.",
                    "code": "workspace_limit_reached",
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(MembershipSerializer(target).data)


class WorkspaceCloseView(APIView):
    permission_classes = [IsAuthenticated, IsTenantMember, RequiresCapability("workspace.manage")]

    def post(self, request):
        try:
            TenantService.close_workspace(actor=request.user, tenant=request.tenant)
        except WorkspaceNotEmpty:
            return Response(
                {"detail": "Remove every other member (or transfer ownership) before closing this workspace."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_200_OK)


class WorkspaceUsageView(APIView):
    """GET /api/workspace/usage/ — the current workspace's member seats vs. plan."""

    permission_classes = [IsAuthenticated, IsTenantMember, RequiresCapability("members.manage")]

    def get(self, request):
        return Response(PlanLimitService.usage_for_workspace(request.tenant))


class AccountUsageView(APIView):
    """GET /api/account/usage/ — workspaces owned vs. plan, per-workspace seats (global)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(PlanLimitService.usage_for_account(request.user))
