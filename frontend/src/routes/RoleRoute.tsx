/**
 * Route-level role gates for the property-billing surfaces (plan §16.5, §20).
 *
 * UX only — a resident who types /subscription is sent to their own dashboard,
 * but the real refusal is server-side (the subscription endpoint returns 403 to a
 * resident; every owner endpoint checks a capability). Nothing here redirects
 * while the workspace list is still loading, so an owner never sees a flash of
 * the wrong page.
 */

import { Navigate, Outlet } from 'react-router-dom'

import { useTenant } from '../lib/tenant'

/** Owner (or no-workspace-yet) surfaces. A resident is sent to /home. */
export function NotForResidents() {
  const { currentTenant } = useTenant()
  if (currentTenant?.role === 'MEMBER') return <Navigate to="/home" replace />
  return <Outlet />
}

/** Workspace-owner property management. Needs an owned, active workspace. */
export function OwnerWorkspaceOnly() {
  const { currentTenant, status } = useTenant()
  if (status === 'empty') return <Navigate to="/workspace" replace />
  if (currentTenant?.role === 'MEMBER') return <Navigate to="/home" replace />
  return <Outlet />
}

/** The resident portal. An owner is sent to their overview. */
export function ResidentOnly() {
  const { currentTenant, status } = useTenant()
  if (status === 'empty') return <Navigate to="/workspace" replace />
  if (currentTenant?.role === 'OWNER') return <Navigate to="/overview" replace />
  return <Outlet />
}
