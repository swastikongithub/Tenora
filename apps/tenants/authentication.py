from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.tenants.models import Membership

# Endpoints that must NOT require X-Tenant-ID because the tenant either
# doesn't exist yet (tenant creation) or genuinely isn't tenant-scoped
# (login, global plan list).
#
# Exact-match set, not a prefix list. A prefix like "/api/tenants/"
# would silently exempt EVERY future route under it — e.g. an
# accidentally-added GET /api/tenants/current/members/ would bypass
# tenant resolution entirely. Exact paths force each new global route
# to be added here deliberately, so the exemption is always a
# conscious decision made at the point a route is created, not an
# accident of URL structure.
#
# Some of these aren't wired up yet (tenant creation/listing land in
# a later step) — listed now so the contract is settled before the
# views exist, not decided ad hoc when each view is written.
GLOBAL_PATHS = frozenset({
    "/api/auth/login/",
    "/api/auth/refresh/",
    "/api/auth/register/",  # POST: create a user (no tenant context possible yet)
    "/api/auth/logout/",   # POST: blacklist a refresh token (not tenant-scoped)
    "/api/auth/verify-email/",         # POST: unauthenticated, no tenant context
    "/api/auth/resend-verification/",  # POST: unauthenticated, no tenant context
    "/api/auth/google/",               # POST: unauthenticated, no tenant context
    "/api/tenants/",       # POST: create a tenant (no tenant context possible yet)
    "/api/tenants/me/",    # GET: tenants the current user belongs to
    "/api/users/me/",      # GET: the requesting user's own {id, email} (identity, not tenant data)
    "/api/plans/",         # GET: public/global plan list
    # Platform-admin (docs/platform-admin-spec.md): deliberately cross-tenant,
    # so there is no single tenant context and no X-Tenant-ID. Access is
    # gated by IsPlatformStaff on the views, not by tenant resolution.
    "/api/platform/tenants/",  # GET: every tenant, platform staff only
    "/api/platform/stats/",    # GET: system-wide aggregates, platform staff only
    # Operator Control Plane, Phase 1 (docs/operator-control-plane-spec.md) —
    # same rationale as the two platform-admin paths above: cross-tenant by
    # design, gated by IsPlatformStaff, not tenant resolution. Detail lookups
    # are a static `.../detail/` path (id passed as a query param), so each
    # is representable here as one more literal string — see
    # apps/platform/views.py's module docstring for why.
    "/api/platform/health/",
    "/api/platform/plans/",
    "/api/platform/plans/detail/",
    "/api/platform/tenants/detail/",
    "/api/platform/webhook-events/",
    "/api/platform/webhook-events/detail/",
    "/api/platform/reconciliation-discrepancies/",
    "/api/platform/users/",
    "/api/platform/users/detail/",
    # Operator Control Plane, Phase 2 (docs/operator-control-plane-spec.md) —
    # the first mutations. Same rationale as Phase 1's entries above.
    "/api/platform/subscriptions/detail/",
    "/api/platform/webhook-events/process-pending/",
    "/api/platform/reconciliation/run/",
    "/api/platform/usage/run/",
    "/api/platform/audit-log/",
    # Operator Control Plane, Phase 3 (docs/operator-control-plane-spec.md) —
    # plan management. Create/edit reuse the two plan paths already listed
    # above (POST on the list path, PATCH on the detail path), so the gateway
    # sync action is the only new literal path this phase adds.
    "/api/platform/plans/sync/",
    # Operator Control Plane, Phase 4 (docs/operator-control-plane-spec.md) —
    # Root tier. Role management is a PATCH on "/api/platform/users/detail/",
    # already listed above, so the raw gateway payload read is the only new
    # literal path. Being listed here exempts it from tenant resolution
    # exactly like its siblings; its own narrower gate is IsPlatformRoot on
    # the view.
    "/api/platform/webhook-events/raw/",
})


class TenantSuspended(APIException):
    """
    The tenant named by X-Tenant-ID exists, the caller is genuinely a member,
    and the tenant has been suspended by a platform operator
    (docs/operator-control-plane-spec.md §F, Phase 5).

    403, not 401: the caller's credentials are fine and re-authenticating would
    change nothing, which is exactly what 401 would invite them to try. It sits
    beside the existing PermissionDenied for "not a member" — both are
    authorization answers about this tenant, not about this token.

    Deliberately a DISTINCT, honest message rather than reusing "you are not a
    member of this tenant". The two are different facts, and the member of a
    suspended workspace is not an attacker to be misled — they are a customer
    who needs to know why their workspace stopped responding. Nothing about
    who suspended it, when, or why is disclosed.
    """

    status_code = 403
    default_detail = (
        "This workspace has been suspended. Contact support for assistance."
    )
    default_code = "tenant_suspended"


class TenantHeaderRequired(APIException):
    """
    A missing or malformed X-Tenant-ID is a client request error, not
    an authentication failure — the JWT itself may be perfectly
    valid. AuthenticationFailed always maps to 401 in DRF, which
    would misrepresent this case, so this is a plain APIException
    with an explicit 400 instead.
    """

    status_code = 400
    default_detail = "X-Tenant-ID header is required and must be a valid UUID."
    default_code = "tenant_header_invalid"


class TenantJWTAuthentication(JWTAuthentication):
    """
    Wraps SimpleJWT's JWTAuthentication to also resolve tenant context
    in the same pass. This exists because a separate Django middleware
    can't safely assume request.user is populated — SimpleJWT
    authenticates at the DRF layer (APIView.perform_authentication),
    which runs after Django's middleware stack has already finished.
    Putting tenant resolution here guarantees the ordering.

    Invariant this class exists to provide: if a tenant-scoped request
    reaches the view, request.tenant and request.membership are
    already resolved and trustworthy. Views and permissions can rely
    on that without re-checking it themselves.
    """

    def authenticate(self, request):
        user_auth = super().authenticate(request)
        if user_auth is None:
            return None

        user, validated_token = user_auth

        if request.path in GLOBAL_PATHS:
            return user, validated_token

        tenant_id = request.headers.get("X-Tenant-ID")
        if not tenant_id:
            raise TenantHeaderRequired()

        try:
            membership = Membership.objects.select_related("tenant").get(
                user=user, tenant_id=tenant_id
            )
        except (DjangoValidationError, ValueError):
            # Header was present but not a valid UUID — still a 400,
            # same as a missing header, not a membership question.
            # Django's UUIDField.to_python raises django.core.exceptions
            # .ValidationError (not a ValueError) for a malformed UUID;
            # ValueError is kept too so the original intent stays explicit.
            raise TenantHeaderRequired()
        except Membership.DoesNotExist:
            # Well-formed tenant_id, but this user has no Membership
            # row for it — a real authorization question, so 403.
            raise PermissionDenied(
                "You are not a member of this tenant.", code="not_a_member"
            )

        # Operator Control Plane Phase 5 (docs/operator-control-plane-spec.md
        # §F) — the ONE check this design adds to this file, sequenced last
        # and reviewed on its own, exactly as §G's migration strategy required.
        #
        # Placed HERE, after membership resolution, on purpose:
        #
        #   - It must not run before the membership check, or a non-member
        #     could probe whether an arbitrary tenant id is suspended — a
        #     small cross-tenant information leak in the one file this
        #     codebase treats as its most security-sensitive.
        #   - It must run before request.tenant is attached, so no view can
        #     ever see a resolved tenant context for a suspended tenant. The
        #     invariant this class exists to provide ("if a tenant-scoped
        #     request reaches the view, request.tenant is resolved and
        #     trustworthy") now also means "and that tenant is not suspended".
        #
        # `membership.tenant` is already loaded by the select_related above, so
        # this adds no query. The whole enforcement is one attribute read.
        #
        # Every platform-operator path is untouched: /api/platform/... is in
        # GLOBAL_PATHS, so this code never runs for it. Suspending a customer
        # cannot lock an operator out of the control plane that would
        # un-suspend them (§5.4).
        if not membership.tenant.is_active:
            raise TenantSuspended()

        # DRF's Request.__getattr__ proxies any attribute not found
        # directly on the Request object to the wrapped HttpRequest
        # (self._request) — this is standard DRF behavior, not a
        # workaround. So attaching here means `request.tenant` and
        # `request.membership` resolve correctly wherever `request`
        # is the DRF Request (views, permissions) further down the
        # stack, with no extra plumbing needed.
        request._request.tenant = membership.tenant
        request._request.membership = membership

        return user, validated_token
