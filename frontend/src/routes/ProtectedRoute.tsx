/**
 * Gate for every authenticated route (spec §4.5).
 *
 *   status 'loading'         -> a neutral full-page loader. NOT a redirect:
 *                              the silent-refresh-on-load must resolve first,
 *                              or a valid reload would flash the login page.
 *   status 'unauthenticated' -> redirect to /login.
 *   status 'authenticated'   -> mount the tenant context + app shell.
 */

import { Navigate } from 'react-router-dom'

import { AppShell, Wordmark } from '../components/layout'
import { useAuth } from '../lib/auth'
import { TenantProvider } from '../lib/tenant'

export function ProtectedRoute() {
  const { status } = useAuth()

  if (status === 'loading') {
    return (
      <div
        className="grid min-h-screen place-items-center bg-base"
        role="status"
        aria-live="polite"
      >
        <div className="flex flex-col items-center gap-3">
          <Wordmark />
          <span className="text-caption text-secondary">Loading&hellip;</span>
        </div>
      </div>
    )
  }

  if (status === 'unauthenticated') {
    return <Navigate to="/login" replace />
  }

  // AppShell renders the matched child route into its own <Outlet>.
  return (
    <TenantProvider>
      <AppShell />
    </TenantProvider>
  )
}
