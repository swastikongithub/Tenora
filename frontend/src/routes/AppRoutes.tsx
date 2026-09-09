/**
 * The route table. Deliberately has no <Router> of its own: App.tsx wraps it in
 * <BrowserRouter>, tests wrap it in <MemoryRouter>.
 */

import { Navigate, Route, Routes } from 'react-router-dom'

import { LoginPage } from './LoginPage'
import { MembersPage } from './MembersPage'
import { OverviewPage } from './OverviewPage'
import { PlatformAdminPage } from './PlatformAdminPage'
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
        {/* Staff-only in effect: PlatformAdminPage redirects non-staff away, and
            the real boundary is IsPlatformStaff on /api/platform/* server-side. */}
        <Route path="platform-admin" element={<PlatformAdminPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
