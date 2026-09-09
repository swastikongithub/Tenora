/**
 * The "the session is over" signal.
 *
 * The API client discovers a dead session (a 401 that a token refresh can't
 * rescue) deep inside a fetch, far from React. Rather than have it reach into
 * auth state or the router directly, it calls `endSession()`, which clears the
 * tokens and notifies every subscriber. `AuthProvider` subscribes and flips its
 * status to unauthenticated; the router then redirects. This keeps the client
 * free of a dependency on React or on the routing layer.
 */

import { clearTokens } from './token-store'

type Listener = () => void

const listeners = new Set<Listener>()

/** Subscribe to session-ended. Returns an unsubscribe function. */
export function onSessionEnded(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/**
 * End the session: clear tokens, then notify. Idempotent — calling it twice
 * (e.g. a failed retry and then an explicit logout) is harmless.
 */
export function endSession(): void {
  clearTokens()
  for (const listener of listeners) listener()
}
