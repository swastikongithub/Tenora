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
    StartCheckoutView,
    SubscriptionWebhookView,
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
    PlatformWebhookEventRawView,
    PlatformWebhookProcessPendingView,
)
from apps.notifications.views import (
    NotificationListView,
    NotificationMarkReadView,
    NotificationPreferenceView,
    NotificationUnreadCountView,
)
from apps.platform.property_views import (
    PlatformMembershipDetailView,
    PlatformPropertyBillDetailView,
    PlatformPropertyBillingSummaryView,
    PlatformPropertyBillListView,
    PlatformPropertyPaymentListView,
    PlatformPropertyReceiptListView,
    PlatformPropertyWorkspaceDetailView,
    PlatformPropertyWorkspaceListView,
    PlatformReadingProofView,
)
from apps.properties import online_payment_views as opv
from apps.properties import views as pv
from apps.tenants.views import (
    AccountUsageView,
    InvitationCancelView,
    InvitationListCreateView,
    InvitationRespondView,
    LeaveWorkspaceView,
    MembershipListCreateView,
    MembershipRemoveView,
    MyInvitationsView,
    MyTenantsView,
    OwnershipTransferView,
    TenantCreateView,
    WorkspaceCloseView,
    WorkspaceUsageView,
)
from apps.users.auth import EmailVerifiedTokenObtainPairView
from apps.users.views import (
    AccountDeleteView,
    AccountPasswordView,
    AccountProfileView,
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
    # --- Operator Control Plane, Phase 4 (docs/operator-control-plane-spec.md) ---
    # Root tier. User role management is PATCH on the existing user detail
    # path (one path, two tiers — see PlatformUserDetailView), so the raw
    # gateway payload read is the only new literal path this phase adds. It is
    # deliberately its own path rather than a flag on the sanitized detail
    # read: a query parameter that widens a response's audience is too easy to
    # copy into a URL and forget.
    path(
        "api/platform/webhook-events/raw/",
        PlatformWebhookEventRawView.as_view(),
        name="platform_webhook_event_raw",
    ),
    # --- Property billing: user-level global paths (in GLOBAL_PATHS) ---
    # docs/TENORA_PROPERTY_BILLING_MASTER_PLAN.md. Notifications, invitations
    # addressed to me, and my account have no single workspace context; each
    # view filters on request.user.
    path("api/notifications/", NotificationListView.as_view(), name="notification_list"),
    path(
        "api/notifications/unread-count/",
        NotificationUnreadCountView.as_view(),
        name="notification_unread_count",
    ),
    path("api/notifications/read/", NotificationMarkReadView.as_view(), name="notification_read"),
    path(
        "api/notifications/preferences/",
        NotificationPreferenceView.as_view(),
        name="notification_preferences",
    ),
    path("api/invitations/mine/", MyInvitationsView.as_view(), name="invitations_mine"),
    path("api/invitations/respond/", InvitationRespondView.as_view(), name="invitation_respond"),
    path("api/account/profile/", AccountProfileView.as_view(), name="account_profile"),
    path("api/account/password/", AccountPasswordView.as_view(), name="account_password"),
    path("api/account/delete/", AccountDeleteView.as_view(), name="account_delete"),
    path("api/account/usage/", AccountUsageView.as_view(), name="account_usage"),
    path("api/account/billing-portfolio/", pv.BillingPortfolioView.as_view(), name="account_billing_portfolio"),
    # --- Platform admin: property billing visibility + workspace roles ---
    path(
        "api/platform/memberships/detail/",
        PlatformMembershipDetailView.as_view(),
        name="platform_membership_detail",
    ),
    path(
        "api/platform/property-billing/summary/",
        PlatformPropertyBillingSummaryView.as_view(),
        name="platform_property_billing_summary",
    ),
    path(
        "api/platform/property-billing/workspaces/",
        PlatformPropertyWorkspaceListView.as_view(),
        name="platform_property_workspaces",
    ),
    path(
        "api/platform/property-billing/workspaces/detail/",
        PlatformPropertyWorkspaceDetailView.as_view(),
        name="platform_property_workspace_detail",
    ),
    path(
        "api/platform/property-billing/bills/",
        PlatformPropertyBillListView.as_view(),
        name="platform_property_bills",
    ),
    path(
        "api/platform/property-billing/bills/detail/",
        PlatformPropertyBillDetailView.as_view(),
        name="platform_property_bill_detail",
    ),
    path(
        "api/platform/property-billing/payments/",
        PlatformPropertyPaymentListView.as_view(),
        name="platform_property_payments",
    ),
    path(
        "api/platform/property-billing/receipts/",
        PlatformPropertyReceiptListView.as_view(),
        name="platform_property_receipts",
    ),
    path(
        "api/platform/property-billing/reading-proof/",
        PlatformReadingProofView.as_view(),
        name="platform_property_reading_proof",
    ),
    # --- tenant-scoped (X-Tenant-ID resolved by TenantJWTAuthentication) ---
    path(
        "api/memberships/",
        MembershipListCreateView.as_view(),
        name="membership_list_create",
    ),
    path("api/memberships/leave/", LeaveWorkspaceView.as_view(), name="membership_leave"),
    path(
        "api/memberships/<uuid:pk>/remove/",
        MembershipRemoveView.as_view(),
        name="membership_remove",
    ),
    path(
        "api/memberships/<uuid:pk>/transfer-ownership/",
        OwnershipTransferView.as_view(),
        name="membership_transfer_ownership",
    ),
    path("api/invitations/", InvitationListCreateView.as_view(), name="invitation_list"),
    path(
        "api/invitations/<uuid:pk>/cancel/",
        InvitationCancelView.as_view(),
        name="invitation_cancel",
    ),
    path("api/workspace/close/", WorkspaceCloseView.as_view(), name="workspace_close"),
    path("api/workspace/usage/", WorkspaceUsageView.as_view(), name="workspace_usage"),
    # Property billing, tenant-scoped (docs/TENORA_PROPERTY_BILLING_MASTER_PLAN.md).
    # Tenant-scoped paths never touch GLOBAL_PATHS, so ordinary `<uuid:pk>`
    # segments are safe here.
    path("api/workspace/settings/", pv.WorkspaceSettingsView.as_view(), name="workspace_settings"),
    path("api/workspace/overview/", pv.WorkspaceOverviewView.as_view(), name="workspace_overview"),
    path("api/residency/", pv.ResidencyView.as_view(), name="residency"),
    path("api/properties/", pv.PropertyListView.as_view(), name="property_list"),
    path("api/properties/<uuid:pk>/", pv.PropertyDetailView.as_view(), name="property_detail"),
    path("api/units/", pv.UnitListView.as_view(), name="unit_list"),
    path("api/units/<uuid:pk>/", pv.UnitDetailView.as_view(), name="unit_detail"),
    path("api/residents/", pv.ResidentListView.as_view(), name="resident_list"),
    path("api/residents/<uuid:pk>/", pv.ResidentDetailView.as_view(), name="resident_detail"),
    path("api/leases/", pv.LeaseListView.as_view(), name="lease_list"),
    path("api/leases/<uuid:pk>/", pv.LeaseDetailView.as_view(), name="lease_detail"),
    path("api/leases/<uuid:pk>/end/", pv.LeaseEndView.as_view(), name="lease_end"),
    path("api/meters/", pv.MeterListView.as_view(), name="meter_list"),
    path("api/meters/<uuid:pk>/", pv.MeterDetailView.as_view(), name="meter_detail"),
    path("api/meter-readings/", pv.MeterReadingListView.as_view(), name="meter_reading_list"),
    path(
        "api/meter-readings/<uuid:pk>/",
        pv.MeterReadingDetailView.as_view(),
        name="meter_reading_detail",
    ),
    path(
        "api/meter-readings/<uuid:pk>/proof/",
        pv.MeterReadingProofView.as_view(),
        name="meter_reading_proof",
    ),
    path(
        "api/meter-readings/<uuid:pk>/correct/",
        pv.MeterReadingCorrectView.as_view(),
        name="meter_reading_correct",
    ),
    path("api/billing/tariffs/", pv.TariffListView.as_view(), name="tariff_list"),
    path("api/billing/cycles/", pv.BillingCycleListView.as_view(), name="billing_cycle_list"),
    path(
        "api/billing/cycles/<uuid:pk>/",
        pv.BillingCycleDetailView.as_view(),
        name="billing_cycle_detail",
    ),
    path(
        "api/billing/cycles/<uuid:pk>/generate/",
        pv.BillingCycleGenerateView.as_view(),
        name="billing_cycle_generate",
    ),
    path(
        "api/billing/cycles/<uuid:pk>/publish/",
        pv.BillingCyclePublishView.as_view(),
        name="billing_cycle_publish",
    ),
    path(
        "api/billing/cycles/<uuid:pk>/close/",
        pv.BillingCycleCloseView.as_view(),
        name="billing_cycle_close",
    ),
    path("api/billing/summary/", pv.BillingSummaryView.as_view(), name="billing_summary"),
    path("api/billing/aging/", pv.BillingAgingView.as_view(), name="billing_aging"),
    path("api/billing/reports/", pv.BillingReportView.as_view(), name="billing_reports"),
    path(
        "api/billing/reminders/run/",
        pv.BillingRemindersRunView.as_view(),
        name="billing_reminders_run",
    ),
    path("api/bills/", pv.BillListView.as_view(), name="bill_list"),
    path("api/bills/<uuid:pk>/", pv.BillDetailView.as_view(), name="bill_detail"),
    path("api/bills/<uuid:pk>/pdf/", pv.BillPdfView.as_view(), name="bill_pdf"),
    # P9 online resident payments (tenant-scoped; body never trusted).
    path("api/bills/<uuid:pk>/online-payment/", opv.BillOnlinePaymentView.as_view(), name="bill_online_payment"),
    path("api/online-payments/", opv.OnlinePaymentListView.as_view(), name="online_payment_list"),
    path("api/online-payments/<uuid:pk>/", opv.OnlinePaymentDetailView.as_view(), name="online_payment_detail"),
    path("api/online-payments/<uuid:pk>/refund/", opv.OnlinePaymentRefundView.as_view(), name="online_payment_refund"),
    path(
        "api/bills/<uuid:pk>/line-items/",
        pv.BillLineItemListView.as_view(),
        name="bill_line_items",
    ),
    path(
        "api/bills/<uuid:pk>/line-items/<uuid:line_id>/",
        pv.BillLineItemDetailView.as_view(),
        name="bill_line_item_detail",
    ),
    path("api/bills/<uuid:pk>/publish/", pv.BillPublishView.as_view(), name="bill_publish"),
    path("api/bills/<uuid:pk>/cancel/", pv.BillCancelView.as_view(), name="bill_cancel"),
    path(
        "api/bills/<uuid:pk>/corrections/",
        pv.BillCorrectionView.as_view(),
        name="bill_corrections",
    ),
    path("api/payments/", pv.PaymentListView.as_view(), name="payment_list"),
    path("api/payments/<uuid:pk>/", pv.PaymentDetailView.as_view(), name="payment_detail"),
    path("api/payments/<uuid:pk>/void/", pv.PaymentVoidView.as_view(), name="payment_void"),
    path("api/receipts/", pv.ReceiptListView.as_view(), name="receipt_list"),
    path("api/receipts/<uuid:pk>/", pv.ReceiptDetailView.as_view(), name="receipt_detail"),
    path("api/receipts/<uuid:pk>/pdf/", pv.ReceiptPdfView.as_view(), name="receipt_pdf"),
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
        SubscriptionWebhookView.as_view(),
        name="razorpay_webhook",
    ),
    # Cashfree Subscriptions for the TENORA subscription (owner -> Tenora).
    # Its own route because Cashfree registers subscription webhooks separately
    # from payment ones, and because a route per provider keeps each one's
    # signature scheme and event vocabulary pinned to the adapter that owns it.
    # The view itself stays provider-neutral: it verifies and parses through
    # whichever adapter `PAYMENT_GATEWAY` names, so this route is live only
    # while that is "cashfree".
    path(
        "api/webhooks/cashfree/subscriptions/",
        SubscriptionWebhookView.as_view(),
        name="cashfree_subscription_webhook",
    ),
    # P9: property-bill payments (resident -> owner). A separate route, gateway
    # and verification from the subscription webhooks above; same no-auth,
    # not-in-GLOBAL_PATHS arrangement for the same reason.
    path(
        "api/webhooks/cashfree/property-payments/",
        opv.CashfreePropertyPaymentWebhookView.as_view(),
        name="cashfree_property_payment_webhook",
    ),
]
