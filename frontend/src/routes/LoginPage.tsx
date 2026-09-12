/**
 * Login — UI spec §C.4 Page 1. Split-panel layout via AuthLayout.
 *
 * Spec §7 / UI spec §C.4: a 401 renders ONE generic message regardless of
 * whether the email exists or the password was wrong — the backend keeps that
 * ambiguous and the UI must not undo it (`messageFor`, unchanged from C2).
 *
 * On success the user goes to /workspace (§C.4: "redirect to workspace
 * selection"), not straight to the app shell — tenant context is chosen there.
 *
 * Login-page redesign — final hierarchy, primary to tertiary:
 *   1. Primary:   Email / Password / Sign in (the existing form, unchanged).
 *   2. Secondary: an "or" divider, then a single centered, compact,
 *      icon-only Google button (GoogleSignInButton's own icon-only
 *      configuration — see that file).
 *   3. Tertiary:  "New here? Create an account", below the Google button.
 * Only the ORDER and the Google button's own sizing changed here — the
 * form markup, its handlers, and AuthArtPanel/AuthLayout are untouched.
 */

import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'

import { Alert, Button, Input } from '../components'
import { useAuth } from '../lib/auth'
import { ApiError } from '../lib/api-error'
import { AuthLayout } from './AuthLayout'
import { GoogleSignInButton } from './GoogleSignInButton'

const GENERIC_CREDENTIALS_ERROR = 'Email or password is incorrect.'

function messageFor(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return GENERIC_CREDENTIALS_ERROR
    if (error.status === 0) {
      return 'Couldn’t reach the server. Check your connection and try again.'
    }
    return 'The server had a problem handling that. Try again in a moment.'
  }
  return 'Something interrupted sign-in. Try again.'
}

export function LoginPage() {
  const { isAuthenticated, login } = useAuth()
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (isAuthenticated) {
    return <Navigate to="/workspace" replace />
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await login(email, password)
      navigate('/workspace', { replace: true })
    } catch (cause) {
      setError(messageFor(cause))
      setSubmitting(false)
    }
  }

  return (
    <AuthLayout heading="Sign in" subheading="Welcome back.">
      {error && (
        <Alert variant="danger" className="mt-6">
          {error}
        </Alert>
      )}

      {/* 1. Primary: email / password / Sign in. */}
      <form onSubmit={onSubmit} className="mt-6 flex flex-col gap-4" noValidate>
        <Input
          label="Email"
          type="email"
          name="email"
          autoComplete="username"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={submitting}
          required
        />
        <Input
          label="Password"
          type="password"
          name="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          disabled={submitting}
          required
        />
        <Button type="submit" className="w-full" loading={submitting}>
          Sign in
        </Button>
      </form>

      {/* 2. Secondary: divider, then a single centered, compact Google button. */}
      <div className="mt-6 flex items-center gap-3 text-caption text-secondary">
        <span className="h-px flex-1 bg-subtle" aria-hidden="true" />
        or
        <span className="h-px flex-1 bg-subtle" aria-hidden="true" />
      </div>

      <div className="mt-6 flex justify-center">
        <GoogleSignInButton
          variant="icon"
          onSuccess={() => navigate('/workspace', { replace: true })}
          onError={setError}
        />
      </div>

      {/* 3. Tertiary: sign-up, below the Google button. */}
      <p className="mt-6 text-body text-secondary">
        New here?{' '}
        <Link
          to="/register"
          className="rounded-sm font-medium text-accent-500 underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-600"
        >
          Create account
        </Link>
      </p>
    </AuthLayout>
  )
}
