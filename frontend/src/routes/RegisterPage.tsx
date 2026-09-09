/**
 * Register — a minimal flow (§4.2). Not fully specified visually anywhere, so it
 * reuses Login's AuthLayout rather than inventing a new language.
 *
 * Fields: email, password, confirm-password. The confirm match is a client-side
 * check before any request — the backend (B1 `RegisterSerializer`) only takes
 * one `password` field.
 *
 * Flow (email-verification-spec.md §4.8): POST /api/auth/register/ → 201
 * {id, email} → a "check your email" confirmation state, with a way to trigger
 * POST /api/auth/resend-verification/ if the email doesn't show up. There is
 * NO auto-login anymore — a freshly registered account is unverified and
 * cannot obtain tokens (apps/users/auth.py's login gate), so attempting one
 * would only ever fail. The account exists the moment registration succeeds;
 * verifying it is a separate step the user completes via the emailed link.
 *
 * Errors: the backend's field-error shape ({"email": [...]} / {"password": [...]})
 * is rendered inline per field via ApiError.fieldErrors. §7: "email already
 * registered" is an unavoidable disclosure for a usable signup form — this is
 * not the same as Login's stricter non-disclosure rule.
 */

import { useState, type FormEvent } from 'react'
import { Link, Navigate } from 'react-router-dom'

import { Alert, Button, Card, Input } from '../components'
import { useAuth } from '../lib/auth'
import { apiClient } from '../lib/api-client'
import { ApiError } from '../lib/api-error'
import { AuthLayout } from './AuthLayout'
import { GoogleSignInButton } from './GoogleSignInButton'

interface FieldErrors {
  email?: string
  password?: string
  confirm?: string
}

function genericMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 0) {
      return 'Couldn’t reach the server. Check your connection and try again.'
    }
    return 'The server had a problem handling that. Try again in a moment.'
  }
  return 'Something interrupted sign-up. Try again.'
}

type ResendState = 'idle' | 'sending' | 'sent'

function CheckYourEmail({ email }: { email: string }) {
  const [resend, setResend] = useState<ResendState>('idle')

  async function onResend() {
    setResend('sending')
    try {
      await apiClient.post('/auth/resend-verification/', { email })
    } catch {
      // The endpoint itself never fails in a way that should change what we
      // show (it's non-disclosing by design) — a transport failure still
      // just falls through to the same confirmation line, matching the
      // backend's "always the identical response" contract in spirit.
    }
    setResend('sent')
  }

  return (
    <Card className="mt-6">
      <h2 className="text-h2 text-primary">Check your email</h2>
      <p className="mt-2 text-body text-secondary">
        We’ve sent a verification link to <strong>{email}</strong>. Click it
        to activate your account.
      </p>

      {resend === 'sent' ? (
        <Alert variant="info" className="mt-4">
          If needed, another verification email has been sent.
        </Alert>
      ) : (
        <Button
          type="button"
          variant="secondary"
          className="mt-4"
          loading={resend === 'sending'}
          onClick={onResend}
        >
          Resend email
        </Button>
      )}

      <p className="mt-6 text-body text-secondary">
        <Link
          to="/login"
          className="rounded-sm font-medium text-accent-500 underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-600"
        >
          Back to sign in
        </Link>
      </p>
    </Card>
  )
}

export function RegisterPage() {
  const { isAuthenticated } = useAuth()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [registeredEmail, setRegisteredEmail] = useState<string | null>(null)

  if (isAuthenticated) {
    return <Navigate to="/workspace" replace />
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFieldErrors({})
    setFormError(null)

    if (password !== confirm) {
      setFieldErrors({ confirm: 'Passwords do not match.' })
      return
    }

    setSubmitting(true)
    try {
      await apiClient.post('/auth/register/', { email, password })
    } catch (cause) {
      setSubmitting(false)
      if (cause instanceof ApiError && Object.keys(cause.fieldErrors).length) {
        setFieldErrors({
          email: cause.fieldErrors.email?.[0],
          password: cause.fieldErrors.password?.[0],
        })
        return
      }
      setFormError(genericMessage(cause))
      return
    }

    setSubmitting(false)
    setRegisteredEmail(email)
  }

  if (registeredEmail) {
    return (
      <AuthLayout
        heading="Create account"
        subheading="Multi-tenant billing infrastructure."
        panelHeadline="Set up billing for your first tenant."
      >
        <CheckYourEmail email={registeredEmail} />
      </AuthLayout>
    )
  }

  return (
    <AuthLayout
      heading="Create account"
      subheading="Multi-tenant billing infrastructure."
      panelHeadline="Set up billing for your first tenant."
    >
      {formError && (
        <Alert variant="danger" className="mt-6">
          {formError}
        </Alert>
      )}

      <div className="mt-6">
        {/* isAuthenticated flips true as soon as this resolves, and the
            early `<Navigate>` above then redirects — no explicit onSuccess
            action needed here, unlike LoginPage's imperative navigate(). */}
        <GoogleSignInButton onSuccess={() => {}} onError={setFormError} />
      </div>

      <div className="mt-6 flex items-center gap-3 text-caption text-secondary">
        <span className="h-px flex-1 bg-subtle" aria-hidden="true" />
        or
        <span className="h-px flex-1 bg-subtle" aria-hidden="true" />
      </div>

      <form onSubmit={onSubmit} className="mt-6 flex flex-col gap-4" noValidate>
        <Input
          label="Email"
          type="email"
          name="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={submitting}
          error={Boolean(fieldErrors.email)}
          helperText={fieldErrors.email}
          required
        />
        <Input
          label="Password"
          type="password"
          name="new-password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          disabled={submitting}
          error={Boolean(fieldErrors.password)}
          helperText={fieldErrors.password}
          required
        />
        <Input
          label="Confirm password"
          type="password"
          name="confirm-password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          disabled={submitting}
          error={Boolean(fieldErrors.confirm)}
          helperText={fieldErrors.confirm}
          required
        />
        <Button type="submit" className="w-full" loading={submitting}>
          Create account
        </Button>
      </form>

      <p className="mt-6 text-body text-secondary">
        Already have an account?{' '}
        <Link
          to="/login"
          className="rounded-sm font-medium text-accent-500 underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-600"
        >
          Sign in
        </Link>
      </p>
    </AuthLayout>
  )
}
