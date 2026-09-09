/**
 * "Sign in with Google" (google-signin-spec.md §4.3). Shared by LoginPage and
 * RegisterPage — a second, independent way to get a session, handled exactly
 * like a successful password login once Google hands back a credential
 * (store tokens, let the caller navigate into the app).
 *
 * Uses the raw Google Identity Services API (`window.google.accounts.id`),
 * not a wrapper package like `@react-oauth/google` — a wrapper would still
 * load this same script from Google's own domain internally (there's no
 * self-hosting it), so it would only add an abstraction to learn, not remove
 * the CDN dependency. The script tag itself lives in index.html, with a
 * comment marking it as the deliberate exception to this project's general
 * anti-CDN preference (§1).
 *
 * The button has no live theme-swap of its own (GIS renders static markup
 * into the container), so it's re-rendered whenever the app's theme flips —
 * `filled_black` chrome in dark mode, `outline` in light — matching every
 * other primitive's dual-theme support rather than reading as a one-off.
 */

import { useEffect, useRef, useState } from 'react'

import { useAuth } from '../lib/auth'
import { ApiError } from '../lib/api-error'
import { GOOGLE_OAUTH_CLIENT_ID } from '../lib/config'
import { useTheme } from '../lib/theme'

interface GoogleCredentialResponse {
  credential: string
}

interface GoogleAccountsId {
  initialize: (config: {
    client_id: string
    callback: (response: GoogleCredentialResponse) => void
  }) => void
  renderButton: (
    parent: HTMLElement,
    options: {
      theme: 'outline' | 'filled_black'
      size: 'large'
      // GIS's own max is 400px, passed as a pixel-number string (not a
      // percentage/keyword) — confirmed against Google's current JS
      // reference (google-signin-spec.md §4.3's "verify, don't assume").
      width: string
    },
  ) => void
}

function getGoogleAccountsId(): GoogleAccountsId | undefined {
  const w = window as unknown as { google?: { accounts?: { id?: GoogleAccountsId } } }
  return w.google?.accounts?.id
}

export interface GoogleSignInButtonProps {
  onSuccess: () => void
  onError: (message: string) => void
}

function genericGoogleError(cause: unknown): string {
  if (cause instanceof ApiError && cause.message) return cause.message
  return 'Google sign-in failed. Try again.'
}

export function GoogleSignInButton({
  onSuccess,
  onError,
}: GoogleSignInButtonProps) {
  const { loginWithGoogle } = useAuth()
  const { theme } = useTheme()
  const containerRef = useRef<HTMLDivElement>(null)
  // Not state — initialize() must only ever run once per page (re-calling it
  // for a theme change would be redundant); only renderButton needs to re-run.
  const initializedRef = useRef(false)
  const [ready, setReady] = useState(() => Boolean(getGoogleAccountsId()))

  // The script is `async defer` — poll briefly until it's parsed rather than
  // assuming it's ready at mount. No client ID means nothing to initialize;
  // the button silently doesn't render rather than erroring the page.
  useEffect(() => {
    if (ready || !GOOGLE_OAUTH_CLIENT_ID) return
    const id = window.setInterval(() => {
      if (getGoogleAccountsId()) {
        setReady(true)
        window.clearInterval(id)
      }
    }, 100)
    return () => window.clearInterval(id)
  }, [ready])

  useEffect(() => {
    if (!ready || !GOOGLE_OAUTH_CLIENT_ID || !containerRef.current) return
    const accountsId = getGoogleAccountsId()
    if (!accountsId) return

    if (!initializedRef.current) {
      initializedRef.current = true
      accountsId.initialize({
        client_id: GOOGLE_OAUTH_CLIENT_ID,
        callback: (response) => {
          loginWithGoogle(response.credential).then(onSuccess, (cause) => {
            onError(genericGoogleError(cause))
          })
        },
      })
    }

    containerRef.current.innerHTML = ''
    accountsId.renderButton(containerRef.current, {
      theme: theme === 'dark' ? 'filled_black' : 'outline',
      size: 'large',
      // AuthLayout's form column is exactly max-w-[400px] (GIS's own max) —
      // fills it edge to edge.
      width: '400',
    })
  }, [ready, theme, loginWithGoogle, onSuccess, onError])

  if (!GOOGLE_OAUTH_CLIENT_ID) return null

  return <div ref={containerRef} />
}
