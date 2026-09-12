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
import { ReconciliationPage } from './admin/ReconciliationPage'
import { TenantDetailPage } from './admin/TenantDetailPage'
import { TenantsPage } from './admin/TenantsPage'
import { UsersPage } from './admin/UsersPage'
import { WebhooksPage } from './admin/WebhooksPage'
import { LoginPage } from './LoginPage'
import { MembersPage } from './MembersPage'
import { OverviewPage } from './OverviewPage'
import { ProtectedRoute } from './ProtectedRoute'
import { RegisterPage } from './RegisterPage'
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
        <Route path="overview" element={<OverviewPage />} />
        <Route path="workspace" element={<WorkspacePage />} />
        <Route path="members" element={<MembersPage />} />
        <Route path="subscription" element={<SubscriptionPage />} />

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
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
