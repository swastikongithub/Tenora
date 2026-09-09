/**
 * The body of the avatar account menu (navbar redesign §4.2). Shows the
 * signed-in email, the theme toggle, and a logout action.
 *
 * Previously this was pinned to the sidebar bottom and carried its own avatar
 * glyph + top border. In the top-navbar layout the avatar is the menu *trigger*
 * (see `AccountMenu`), so this component is just the stacked contents.
 *
 * Email resolution is unchanged (Stage C3 §4.4) — now via the shared
 * `useCurrentUser` hook: `AuthProvider.userEmail` when the login form set it
 * this session, otherwise `GET /api/users/me/` keyed globally so it survives a
 * tenant switch, otherwise a neutral label if that request fails (§8).
 */

import { useNavigate } from 'react-router-dom'

import { useAuth } from '../../lib/auth'
import { Button, Skeleton } from '../index'
import { ThemeToggle } from './ThemeToggle'
import { useCurrentUser } from './use-current-user'

export function UserMenu() {
  const { logout } = useAuth()
  const navigate = useNavigate()
  const { email, resolving } = useCurrentUser()

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="px-1">
        {resolving ? (
          <Skeleton width={160} height={12} label="Loading your account" />
        ) : (
          <span className="block truncate text-caption text-secondary">
            {email ?? 'Signed in'}
          </span>
        )}
      </div>
      <ThemeToggle />
      <Button variant="ghost" size="sm" onClick={handleLogout}>
        Log out
      </Button>
    </div>
  )
}
