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
from apps.platform.views import PlatformStatsView, PlatformTenantListView
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
