/**
 * The in-app notification entry point in the top bar: a bell with the unread
 * count, linking to /notifications. The count is the caller's own (a global
 * endpoint filtered on the authenticated user). If it can't be loaded, the bell
 * simply shows no count — the shell never renders an error for it.
 */

import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { apiClient } from '../../lib/api-client'
import { queryKeys } from '../../lib/query-keys'

export function NotificationBell() {
  const { data } = useQuery({
    queryKey: queryKeys.notificationsUnread(),
    queryFn: () => apiClient.get<{ unread: number }>('/notifications/unread-count/'),
    refetchInterval: 60_000,
  })
  const unread = data?.unread ?? 0
  return (
    <Link
      to="/notifications"
      aria-label={unread ? `Notifications, ${unread} unread` : 'Notifications'}
      className="relative grid size-8 place-items-center rounded-full text-secondary hover:text-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-600"
    >
      <svg className="size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} aria-hidden="true">
        <path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0" />
      </svg>
      {unread > 0 && (
        <span className="absolute -right-0.5 -top-0.5 grid min-w-4 place-items-center rounded-full bg-danger px-1 text-[10px] font-medium leading-4 text-[var(--color-base)]">
          {unread > 99 ? '99+' : unread}
        </span>
      )}
    </Link>
  )
}
