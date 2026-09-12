/**
 * Shared shell for every /admin/* page — docs/operator-control-plane-spec.md
 * §D: "/admin is the canonical operator surface... nested under the same
 * ProtectedRoute gate."
 *
 * The staff gate here is UX ONLY, exactly as the retired PlatformAdminPage
 * documented about itself — the real boundary is IsPlatformStaff on every
 * /api/platform/* endpoint server-side, which returns 403 to any non-staff
 * caller regardless of what renders here. Every /admin/* child route sits
 * behind this ONE gate (not re-implemented per page) — a non-staff visitor
 * to any nested path (e.g. /admin/plans) is redirected here too, since
 * AdminLayout is the parent route element for all of them.
 *
 * The tab strip reuses TopNavbar's own underline-active-tab convention
 * (weight + colour + an accent underline) rather than inventing a new
 * visual idiom — no redesign in this phase (spec task §10).
 */

import { NavLink, Navigate, Outlet } from 'react-router-dom'

import { useCurrentUser } from '../../components/layout/use-current-user'
import { cn } from '../../lib/cn'

interface AdminNavItem {
  to: string
  label: string
  end?: boolean
}

const ADMIN_NAV_ITEMS: AdminNavItem[] = [
  { to: '/admin', label: 'Overview', end: true },
  { to: '/admin/plans', label: 'Plans' },
  { to: '/admin/tenants', label: 'Tenants' },
  { to: '/admin/billing-events', label: 'Billing Events' },
  { to: '/admin/webhooks', label: 'Webhooks' },
  { to: '/admin/reconciliation', label: 'Reconciliation' },
  { to: '/admin/users', label: 'Users' },
  { to: '/admin/audit-log', label: 'Audit Log' },
]

const tabLinkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    'flex h-10 shrink-0 items-center border-b-2 px-1 text-label transition-colors',
    'focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent-600',
    isActive
      ? 'border-accent-600 font-medium text-primary'
      : 'border-transparent text-secondary hover:text-primary',
  )

export function AdminLayout() {
  const { isStaff, isStaffResolving } = useCurrentUser()

  // `isStaffResolving` (not a generic "loading"), same reasoning
  // PlatformAdminPage.tsx documented: a staff member who just logged in
  // must not see a false "access denied" flash while /users/me/ is still
  // in flight.
  if (isStaffResolving) {
    return (
      <div
        className="grid min-h-[40vh] place-items-center text-secondary"
        role="status"
        aria-live="polite"
      >
        <span className="text-body">Loading&hellip;</span>
      </div>
    )
  }

  if (!isStaff) {
    return <Navigate to="/overview" replace />
  }

  return (
    <section className="mx-auto max-w-6xl">
      <h1 className="text-display text-primary">Platform Admin</h1>
      <p className="mt-1 text-body text-secondary">
        Operator control plane — every tenant and subscription across the
        system. Phase 1: read-only.
      </p>

      <nav aria-label="Platform admin sections" className="mt-6 border-b border-subtle">
        <ul className="flex gap-6 overflow-x-auto">
          {ADMIN_NAV_ITEMS.map((item) => (
            <li key={item.to}>
              <NavLink to={item.to} end={item.end} className={tabLinkClass}>
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <div className="mt-6">
        <Outlet />
      </div>
    </section>
  )
}
