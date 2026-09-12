"""
Root URLconf.

Deliberately only wires what actually exists at each step. Plan and
subscription routes are added here as their views are built in the
following steps — not stubbed in ahead of time, so this file never
claims to serve a route that would 404 or error if hit.

Every path below that is exempt from tenant resolution must appear
verbatim in apps/tenants/authentication.py GLOBAL_PATHS — that set is
exact-match, so a path here that drifts from the one there silently
becomes tenant-scoped (or vice versa).
"""

from django.contrib import admin
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from apps.billing.views import (
    ConfirmCheckoutView,
    CurrentSubscriptionView,
    PlanListView,
    RazorpayWebhookView,
    StartCheckoutView,
)
from apps.platform.views import (
    PlatformAuditLogListView,
    PlatformHealthView,
    PlatformPlanDetailView,
    PlatformPlanListView,
    PlatformPlanSyncView,
    PlatformReconciliationDiscrepancyListView,
    PlatformReconciliationRunView,
    PlatformStatsView,
    PlatformSubscriptionDetailView,
    PlatformTenantDetailView,
    PlatformTenantListView,
    PlatformUsageRunView,
    PlatformUserDetailView,
    PlatformUserListView,
    PlatformWebhookEventDetailView,
    PlatformWebhookEventListView,
    PlatformWebhookProcessPendingView,
)
from apps.tenants.views import (
    MembershipListCreateView,
    MyTenantsView,
    TenantCreateView,
)
from apps.users.auth import EmailVerifiedTokenObtainPairView
from apps.users.views import (
    GoogleSignInView,
    LogoutView,
    MeView,
    RegisterView,
    ResendVerificationView,
    VerifyEmailView,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    # --- global paths (in GLOBAL_PATHS, no X-Tenant-ID) ---
    path(
        "api/auth/login/",
        EmailVerifiedTokenObtainPairView.as_view(),
        name="token_obtain_pair",
    ),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/auth/register/", RegisterView.as_view(), name="register"),
    path("api/auth/logout/", LogoutView.as_view(), name="logout"),
    path(
        "api/auth/verify-email/", VerifyEmailView.as_view(), name="verify_email"
    ),
    path(
        "api/auth/resend-verification/",
        ResendVerificationView.as_view(),
        name="resend_verification",
    ),
    path("api/auth/google/", GoogleSignInView.as_view(), name="google_signin"),
    path("api/tenants/", TenantCreateView.as_view(), name="tenant_create"),
    path("api/tenants/me/", MyTenantsView.as_view(), name="tenants_me"),
    path("api/users/me/", MeView.as_view(), name="users_me"),
    path("api/plans/", PlanListView.as_view(), name="plan_list"),
    path(
        "api/platform/tenants/",
        PlatformTenantListView.as_view(),
        name="platform_tenants",
    ),
    path(
        "api/platform/stats/",
        PlatformStatsView.as_view(),
        name="platform_stats",
    ),
    # --- Operator Control Plane, Phase 1 (docs/operator-control-plane-spec.md) ---
    # Read-only. Detail lookups are `?id=` on a static path, not a `<uuid:pk>`
    # segment — see apps/platform/views.py's module docstring for why.
    path("api/platform/health/", PlatformHealthView.as_view(), name="platform_health"),
    path(
        "api/platform/plans/", PlatformPlanListView.as_view(), name="platform_plan_list"
    ),
    path(
        "api/platform/plans/detail/",
        PlatformPlanDetailView.as_view(),
        name="platform_plan_detail",
    ),
    # --- Operator Control Plane, Phase 3 (docs/operator-control-plane-spec.md) ---
    # Plan management. Create is POST on the existing list path and edit is
    # PATCH on the existing detail path, so Phase 3 adds exactly ONE new
    # literal path here (and one to GLOBAL_PATHS): the gateway sync action.
    path(
        "api/platform/plans/sync/",
        PlatformPlanSyncView.as_view(),
        name="platform_plan_sync",
    ),
    path(
        "api/platform/tenants/detail/",
        PlatformTenantDetailView.as_view(),
        name="platform_tenant_detail",
    ),
    path(
        "api/platform/webhook-events/",
        PlatformWebhookEventListView.as_view(),
        name="platform_webhook_event_list",
    ),
    path(
        "api/platform/webhook-events/detail/",
        PlatformWebhookEventDetailView.as_view(),
        name="platform_webhook_event_detail",
    ),
    path(
        "api/platform/reconciliation-discrepancies/",
        PlatformReconciliationDiscrepancyListView.as_view(),
        name="platform_reconciliation_discrepancy_list",
    ),
    path("api/platform/users/", PlatformUserListView.as_view(), name="platform_user_list"),
    path(
        "api/platform/users/detail/",
        PlatformUserDetailView.as_view(),
        name="platform_user_detail",
    ),
    # --- Operator Control Plane, Phase 2 (docs/operator-control-plane-spec.md) ---
    # The first mutations. Subscription detail is `.../detail/?id=`, same
    # static-path convention as the Phase 1 detail views, same reason.
    path(
        "api/platform/subscriptions/detail/",
        PlatformSubscriptionDetailView.as_view(),
        name="platform_subscription_detail",
    ),
    path(
        "api/platform/webhook-events/process-pending/",
        PlatformWebhookProcessPendingView.as_view(),
        name="platform_webhook_process_pending",
    ),
    path(
        "api/platform/reconciliation/run/",
        PlatformReconciliationRunView.as_view(),
        name="platform_reconciliation_run",
    ),
    path(
        "api/platform/usage/run/",
        PlatformUsageRunView.as_view(),
        name="platform_usage_run",
    ),
    path(
        "api/platform/audit-log/",
        PlatformAuditLogListView.as_view(),
        name="platform_audit_log",
    ),
    # --- tenant-scoped (X-Tenant-ID resolved by TenantJWTAuthentication) ---
    path(
        "api/memberships/",
        MembershipListCreateView.as_view(),
        name="membership_list_create",
    ),
    path(
        "api/subscriptions/current/",
        CurrentSubscriptionView.as_view(),
        name="subscription_current",
    ),
    path(
        "api/subscriptions/current/checkout/",
        StartCheckoutView.as_view(),
        name="subscription_checkout_start",
    ),
    path(
        "api/subscriptions/current/confirm-checkout/",
        ConfirmCheckoutView.as_view(),
        name="subscription_checkout_confirm",
    ),
    # --- webhooks (unauthenticated; the signature check IS the auth) ---
    # Deliberately NOT in GLOBAL_PATHS: the view sets authentication_classes=[]
    # so TenantJWTAuthentication never runs, and adding it there would only
    # force a mirror change to the frontend's global-paths list for a route the
    # frontend never calls.
    path(
        "api/webhooks/razorpay/",
        RazorpayWebhookView.as_view(),
        name="razorpay_webhook",
    ),
]
