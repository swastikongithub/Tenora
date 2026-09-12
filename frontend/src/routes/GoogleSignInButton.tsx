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
 *
 * Login-page redesign: the task scope is explicitly the login page only
 * ("do not redesign the rest of the approved login page" — and RegisterPage
 * is a different page). `variant` defaults to `'full'`, GIS's original
 * full-width text button, so RegisterPage's call site (unchanged) renders
 * exactly as it did before. LoginPage opts into `variant="icon"` — GIS's
 * OWN icon-only configuration (`type: 'icon'`), a compact, circular,
 * Google-drawn control. Both are Google's own official renderings; only the
 * `type`/`shape`/`width` options passed to `renderButton` differ. The
 * wrapping `role="group"` + `aria-label` exists because GIS's button is
 * rendered asynchronously by Google's own script (a no-op in this project's
 * test doubles, which stub `renderButton` entirely) — the label makes "an
 * accessible name exists for this control" true and verifiable independent
 * of Google's own internal rendering.
 */

import { useEffect, useRef, useState } from 'react'

import { useAuth } from '../lib/auth'
import { ApiError } from '../lib/api-error'
import { GOOGLE_OAUTH_CLIENT_ID } from '../lib/config'
import { useTheme } from '../lib/theme'

interface GoogleCredentialResponse {
  credential: string
}

type RenderButtonOptions =
  | {
      theme: 'outline' | 'filled_black'
      size: 'large'
      // GIS's own max is 400px, passed as a pixel-number string (not a
      // percentage/keyword) — confirmed against Google's current JS
      // reference (google-signin-spec.md §4.3's "verify, don't assume").
      width: string
    }
  | {
      theme: 'outline' | 'filled_black'
      size: 'large'
      // Google's official icon-only button configuration — a compact,
      // circular, Google-drawn control (not a recreation of their
      // branding). No `width` option applies to this type.
      type: 'icon'
      shape: 'circle'
    }

interface GoogleAccountsId {
  initialize: (config: {
    client_id: string
    callback: (response: GoogleCredentialResponse) => void
  }) => void
  renderButton: (parent: HTMLElement, options: RenderButtonOptions) => void
}

function getGoogleAccountsId(): GoogleAccountsId | undefined {
  const w = window as unknown as { google?: { accounts?: { id?: GoogleAccountsId } } }
  return w.google?.accounts?.id
}

export interface GoogleSignInButtonProps {
  onSuccess: () => void
  onError: (message: string) => void
  /**
   * `'full'` (default) — GIS's original full-width text button, exactly as
   * it rendered before the login-page redesign; RegisterPage relies on
   * this default and passes nothing here.
   * `'icon'` — GIS's compact, icon-only, circular button; LoginPage only.
   */
  variant?: 'full' | 'icon'
}

function genericGoogleError(cause: unknown): string {
  if (cause instanceof ApiError && cause.message) return cause.message
  return 'Google sign-in failed. Try again.'
}

export function GoogleSignInButton({
  onSuccess,
  onError,
  variant = 'full',
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
    const baseTheme = theme === 'dark' ? 'filled_black' : 'outline'
    accountsId.renderButton(
      containerRef.current,
      variant === 'icon'
        ? { theme: baseTheme, size: 'large', type: 'icon', shape: 'circle' }
        : // AuthLayout's form column is exactly max-w-[400px] (GIS's own
          // max) — fills it edge to edge, unchanged from before the redesign.
          { theme: baseTheme, size: 'large', width: '400' },
    )
  }, [ready, theme, variant, loginWithGoogle, onSuccess, onError])

  if (!GOOGLE_OAUTH_CLIENT_ID) return null

  return (
    // h-10 reserves the same 40px row Button's md size uses (the "Sign in" /
    // "Create account" buttons) — GIS's own "large" size renders at that
    // same height, so this doesn't change how the button looks once loaded.
    // What it does fix: without a reserved height, this container is 0px
    // tall until the async Google script paints the button, so the "or"
    // divider and whatever sits below it visibly jump the moment it loads —
    // reserving the row up front keeps every surrounding gap (divider →
    // Google → sign-up link) fixed from first paint, identically on every
    // page that uses this component.
    <div
      role="group"
      aria-label="Sign in with Google"
      title="Sign in with Google"
      className="flex h-10 items-center justify-center"
    >
      <div ref={containerRef} />
    </div>
  )
}
