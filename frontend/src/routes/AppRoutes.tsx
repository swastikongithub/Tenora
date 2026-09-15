/**
 * The route table. Deliberately has no <Router> of its own: App.tsx wraps it in
 * <BrowserRouter>, tests wrap it in <MemoryRouter>.
 */

import { Navigate, Route, Routes } from 'react-router-dom'

import { lazyPage } from './lazy-page'
import { LoginPage } from './LoginPage'
import { ProtectedRoute } from './ProtectedRoute'
import { RegisterPage } from './RegisterPage'
import { NotForResidents, OwnerWorkspaceOnly, ResidentOnly } from './RoleRoute'
import { VerifyEmailPage } from './VerifyEmailPage'

// Route-level code splitting (landing plan H-D5). The public landing page, the
// workspace app and the operator console each load only when first visited;
// the auth pages and route guards stay in the entry chunk.
const LandingPage = lazyPage(() => import('../landing/LandingPage'), 'LandingPage')

const AdminLayout = lazyPage(() => import('./admin/AdminLayout'), 'AdminLayout')
const AdminOverviewPage = lazyPage(() => import('./admin/AdminOverviewPage'), 'AdminOverviewPage')
const AuditLogPage = lazyPage(() => import('./admin/AuditLogPage'), 'AuditLogPage')
const BillingEventsPage = lazyPage(() => import('./admin/BillingEventsPage'), 'BillingEventsPage')
const PlanDetailPage = lazyPage(() => import('./admin/PlanDetailPage'), 'PlanDetailPage')
const PlansPage = lazyPage(() => import('./admin/PlansPage'), 'PlansPage')
const PropertyBillAdminPage = lazyPage(() => import('./admin/PropertyBillingPages'), 'PropertyBillAdminPage')
const PropertyBillingAdminPage = lazyPage(() => import('./admin/PropertyBillingPages'), 'PropertyBillingAdminPage')
const PropertyWorkspaceAdminPage = lazyPage(() => import('./admin/PropertyBillingPages'), 'PropertyWorkspaceAdminPage')
const PropertyWorkspaceBillsAdminPage = lazyPage(
  () => import('./admin/PropertyBillingPages'),
  'PropertyWorkspaceBillsAdminPage',
)
const ReconciliationPage = lazyPage(() => import('./admin/ReconciliationPage'), 'ReconciliationPage')
const TenantDetailPage = lazyPage(() => import('./admin/TenantDetailPage'), 'TenantDetailPage')
const TenantsPage = lazyPage(() => import('./admin/TenantsPage'), 'TenantsPage')
const UsersPage = lazyPage(() => import('./admin/UsersPage'), 'UsersPage')
const WebhooksPage = lazyPage(() => import('./admin/WebhooksPage'), 'WebhooksPage')

const MembersPage = lazyPage(() => import('./MembersPage'), 'MembersPage')
const NotificationsPage = lazyPage(() => import('./NotificationsPage'), 'NotificationsPage')
const OverviewPage = lazyPage(() => import('./OverviewPage'), 'OverviewPage')
const SettingsPage = lazyPage(() => import('./SettingsPage'), 'SettingsPage')
const SubscriptionPage = lazyPage(() => import('./SubscriptionPage'), 'SubscriptionPage')
const WorkspacePage = lazyPage(() => import('./WorkspacePage'), 'WorkspacePage')

const BillDetailPage = lazyPage(() => import('./property/BillDetailPage'), 'BillDetailPage')
const AgingPage = lazyPage(() => import('./property/BillingPages'), 'AgingPage')
const BillingLayout = lazyPage(() => import('./property/BillingPages'), 'BillingLayout')
const BillingOverviewPage = lazyPage(() => import('./property/BillingPages'), 'BillingOverviewPage')
const BillsPage = lazyPage(() => import('./property/BillingPages'), 'BillsPage')
const ReadingsPage = lazyPage(() => import('./property/BillingPages'), 'ReadingsPage')
const ReportsPage = lazyPage(() => import('./property/BillingPages'), 'ReportsPage')
const TariffsPage = lazyPage(() => import('./property/BillingPages'), 'TariffsPage')
const PaymentsPage = lazyPage(() => import('./property/PaymentPages'), 'PaymentsPage')
const ReceiptPage = lazyPage(() => import('./property/PaymentPages'), 'ReceiptPage')
const ReceiptsPage = lazyPage(() => import('./property/PaymentPages'), 'ReceiptsPage')
const PortfolioPage = lazyPage(() => import('./property/PortfolioPage'), 'PortfolioPage')
const OnboardingPage = lazyPage(() => import('./property/PropertyPages'), 'OnboardingPage')
const PropertiesPage = lazyPage(() => import('./property/PropertyPages'), 'PropertiesPage')
const PropertyDetailPage = lazyPage(() => import('./property/PropertyPages'), 'PropertyDetailPage')
const ResidentDetailPage = lazyPage(() => import('./property/PropertyPages'), 'ResidentDetailPage')
const ResidentsPage = lazyPage(() => import('./property/PropertyPages'), 'ResidentsPage')
const UnitDetailPage = lazyPage(() => import('./property/PropertyPages'), 'UnitDetailPage')
const ResidentBillsPage = lazyPage(() => import('./property/ResidentPages'), 'ResidentBillsPage')
const ResidentHomePage = lazyPage(() => import('./property/ResidentPages'), 'ResidentHomePage')

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/verify-email" element={<VerifyEmailPage />} />

      {/* Public marketing page (docs/TENORA_LANDING_PAGE_PLAN.md). Shown to
          signed-in visitors too, with "Open workspace" in its nav (H-D2). */}
      <Route path="/" element={<LandingPage />} />

      {/* Every authenticated route. A pathless layout: the child paths below
          resolve exactly as they did under the old "/" parent. */}
      <Route element={<ProtectedRoute />}>
        <Route path="workspace" element={<WorkspacePage />} />
        <Route path="members" element={<MembersPage />} />

        {/* The Tenora subscription and the workspace overview are the OWNER's
            relationship with Tenora — a resident is redirected to their own
            dashboard (and refused server-side regardless). */}
        <Route element={<NotForResidents />}>
          <Route path="overview" element={<OverviewPage />} />
          <Route path="subscription" element={<SubscriptionPage />} />
        </Route>

        {/* Property billing — owner surfaces (docs/TENORA_PROPERTY_BILLING_MASTER_PLAN.md). */}
        <Route element={<OwnerWorkspaceOnly />}>
          <Route path="onboarding" element={<OnboardingPage />} />
          <Route path="properties" element={<PropertiesPage />} />
          <Route path="properties/:id" element={<PropertyDetailPage />} />
          <Route path="units/:id" element={<UnitDetailPage />} />
          <Route path="residents" element={<ResidentsPage />} />
          <Route path="residents/:id" element={<ResidentDetailPage />} />
          <Route path="payments" element={<PaymentsPage />} />
          <Route path="billing" element={<BillingLayout />}>
            <Route index element={<BillingOverviewPage />} />
            <Route path="bills" element={<BillsPage />} />
            <Route path="aging" element={<AgingPage />} />
            <Route path="readings" element={<ReadingsPage />} />
            <Route path="tariffs" element={<TariffsPage />} />
            <Route path="reports" element={<ReportsPage />} />
            <Route path="portfolio" element={<PortfolioPage />} />
          </Route>
        </Route>

        {/* Property billing — the resident portal. */}
        <Route element={<ResidentOnly />}>
          <Route path="home" element={<ResidentHomePage />} />
          <Route path="my-bills" element={<ResidentBillsPage mode="open" />} />
          <Route path="billing-history" element={<ResidentBillsPage mode="history" />} />
        </Route>

        {/* Shared, role-aware: the API scopes each to what the viewer may see. */}
        <Route path="bills/:id" element={<BillDetailPage />} />
        <Route path="receipts" element={<ReceiptsPage />} />
        <Route path="receipts/:id" element={<ReceiptPage />} />
        <Route path="notifications" element={<NotificationsPage />} />
        <Route path="settings" element={<SettingsPage />} />

        {/* Compatibility redirect only — docs/operator-control-plane-spec.md
            §D: "/admin is canonical... /platform-admin becomes a
            compatibility redirect... never duplicated." No page renders at
            this path anymore. */}
        <Route path="platform-admin" element={<Navigate to="/admin" replace />} />

        {/* Operator Control Plane (docs/operator-control-plane-spec.md).
            Staff-only in effect: AdminLayout redirects non-staff away (one
            gate, shared by every child route below — not re-implemented per
            page), and the real boundary is IsPlatformStaff on
            /api/platform/* server-side. */}
        <Route path="admin" element={<AdminLayout />}>
          <Route index element={<AdminOverviewPage />} />
          <Route path="plans" element={<PlansPage />} />
          <Route path="plans/:id" element={<PlanDetailPage />} />
          <Route path="tenants" element={<TenantsPage />} />
          <Route path="tenants/:id" element={<TenantDetailPage />} />
          <Route path="billing-events" element={<BillingEventsPage />} />
          <Route path="webhooks" element={<WebhooksPage />} />
          <Route path="reconciliation" element={<ReconciliationPage />} />
          <Route path="users" element={<UsersPage />} />
          <Route path="audit-log" element={<AuditLogPage />} />
          <Route path="property-billing" element={<PropertyBillingAdminPage />} />
          <Route path="property-billing/bills/:billId" element={<PropertyBillAdminPage />} />
          <Route path="property-billing/:id" element={<PropertyWorkspaceAdminPage />} />
          <Route path="property-billing/:id/bills" element={<PropertyWorkspaceBillsAdminPage />} />
        </Route>
      </Route>

      {/* Unknown paths keep the destination they had before "/" became the
          public landing page: signed out -> /login, owner -> /overview,
          resident -> /home (via the guards). */}
      <Route path="*" element={<Navigate to="/overview" replace />} />
    </Routes>
  )
}
