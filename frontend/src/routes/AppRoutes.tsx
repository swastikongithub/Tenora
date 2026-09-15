/**
 * The route table. Deliberately has no <Router> of its own: App.tsx wraps it in
 * <BrowserRouter>, tests wrap it in <MemoryRouter>.
 */

import { Navigate, Route, Routes } from 'react-router-dom'

import { AdminLayout } from './admin/AdminLayout'
import { AdminOverviewPage } from './admin/AdminOverviewPage'
import { AuditLogPage } from './admin/AuditLogPage'
import { BillingEventsPage } from './admin/BillingEventsPage'
import { PlanDetailPage } from './admin/PlanDetailPage'
import { PlansPage } from './admin/PlansPage'
import {
  PropertyBillAdminPage,
  PropertyBillingAdminPage,
  PropertyWorkspaceAdminPage,
  PropertyWorkspaceBillsAdminPage,
} from './admin/PropertyBillingPages'
import { ReconciliationPage } from './admin/ReconciliationPage'
import { TenantDetailPage } from './admin/TenantDetailPage'
import { TenantsPage } from './admin/TenantsPage'
import { UsersPage } from './admin/UsersPage'
import { WebhooksPage } from './admin/WebhooksPage'
import { LoginPage } from './LoginPage'
import { MembersPage } from './MembersPage'
import { NotificationsPage } from './NotificationsPage'
import { OverviewPage } from './OverviewPage'
import { BillDetailPage } from './property/BillDetailPage'
import {
  AgingPage,
  BillingLayout,
  BillingOverviewPage,
  BillsPage,
  ReadingsPage,
  ReportsPage,
  TariffsPage,
} from './property/BillingPages'
import { PaymentsPage, ReceiptPage, ReceiptsPage } from './property/PaymentPages'
import { PortfolioPage } from './property/PortfolioPage'
import {
  OnboardingPage,
  PropertiesPage,
  PropertyDetailPage,
  ResidentDetailPage,
  ResidentsPage,
  UnitDetailPage,
} from './property/PropertyPages'
import { ResidentBillsPage, ResidentHomePage } from './property/ResidentPages'
import { ProtectedRoute } from './ProtectedRoute'
import { RegisterPage } from './RegisterPage'
import { NotForResidents, OwnerWorkspaceOnly, ResidentOnly } from './RoleRoute'
import { SettingsPage } from './SettingsPage'
import { SubscriptionPage } from './SubscriptionPage'
import { VerifyEmailPage } from './VerifyEmailPage'
import { WorkspacePage } from './WorkspacePage'

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/verify-email" element={<VerifyEmailPage />} />

      <Route path="/" element={<ProtectedRoute />}>
        <Route index element={<Navigate to="/overview" replace />} />
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

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
