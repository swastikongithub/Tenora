/**
 * The verify-email landing route (email-verification-spec.md §4.9). Public,
 * outside ProtectedRoute — reached by clicking the link in the verification
 * email, so the visitor is never authenticated here.
 *
 * Reads `token` from the query string and calls
 * POST /api/auth/verify-email/ once on mount. The backend's 400 body is
 * already one generic { "detail": "..." } message covering invalid/expired/
 * already-used (ApiError.fromBody maps a bare `detail` straight into
 * `.message`) — this page just renders it, it never tries to distinguish
 * the cases itself. A missing token param renders the same failure state
 * without making a request at all.
 */

import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { Alert, Button, Card, Input } from '../components'
import { apiClient } from '../lib/api-client'
import { ApiError } from '../lib/api-error'
import { AuthLayout } from './AuthLayout'

type Status = 'pending' | 'success' | 'error'

const MISSING_TOKEN_MESSAGE =
  'This verification link is missing its token. Check the link you followed, or request a new one.'

function ResendForm() {
  const [email, setEmail] = useState('')
  const [sending, setSending] = useState(false)
  const [sent, setSent] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setSending(true)
    try {
      await apiClient.post('/auth/resend-verification/', { email })
    } catch {
      // Non-disclosing endpoint by design — no distinguishable failure to
      // surface differently here either.
    }
    setSending(false)
    setSent(true)
  }

  if (sent) {
    return (
      <Alert variant="info" className="mt-4">
        If an account with that email exists and isn’t verified yet, we’ve
        sent a new verification link.
      </Alert>
    )
  }

  return (
    <form onSubmit={onSubmit} className="mt-4 flex flex-col gap-3" noValidate>
      <Input
        label="Email"
        type="email"
        name="email"
        autoComplete="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        disabled={sending}
        required
      />
      <Button type="submit" variant="secondary" loading={sending}>
        Send a new link
      </Button>
    </form>
  )
}

export function VerifyEmailPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')

  const [status, setStatus] = useState<Status>('pending')
  const [message, setMessage] = useState<string>('')
  // The verify-email token is single-use — a second POST with the same
  // token fails with "already used." StrictMode's double effect invocation
  // (mount → cleanup → mount) would otherwise fire this request twice, and
  // here that's worse than a redundant call: whichever request reaches the
  // server second gets the genuine "already used" rejection, showing a
  // false failure for a verification that actually succeeded. firedRef
  // guards that — never reset, so the request fires exactly once, ever.
  //
  // That alone isn't enough, though: the one real request is started inside
  // the FIRST effect invocation, whose own `cancelled`-style cleanup runs
  // (as part of StrictMode's phantom cycle) before that request resolves —
  // the exact trap AuthProvider's bootstrap effect hit (see its comment).
  // mountedRef fixes it the same way: reset to true at the top of every
  // effect invocation (so the second, surviving invocation un-cancels it),
  // and only left false by whichever cleanup turns out to be the real one.
  const firedRef = useRef(false)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true

    if (!token) {
      setStatus('error')
      setMessage(MISSING_TOKEN_MESSAGE)
      return
    }

    if (!firedRef.current) {
      firedRef.current = true
      apiClient
        .post('/auth/verify-email/', { token })
        .then(() => {
          if (mountedRef.current) setStatus('success')
        })
        .catch((cause: unknown) => {
          if (!mountedRef.current) return
          const detail =
            cause instanceof ApiError && cause.message
              ? cause.message
              : 'This verification link is invalid or has expired.'
          setMessage(detail)
          setStatus('error')
        })
    }

    return () => {
      mountedRef.current = false
    }
  }, [token])

  return (
    <AuthLayout heading="Verify your email" subheading="Multi-tenant billing infrastructure.">
      <Card className="mt-6">
        {status === 'pending' && (
          <p className="text-body text-secondary">Verifying your email…</p>
        )}

        {status === 'success' && (
          <>
            <h2 className="text-h2 text-primary">You’re verified</h2>
            <p className="mt-2 text-body text-secondary">
              Your email is confirmed. You can sign in now.
            </p>
            <Link
              to="/login"
              className="mt-4 inline-block rounded-sm font-medium text-accent-500 underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-600"
            >
              Sign in
            </Link>
          </>
        )}

        {status === 'error' && (
          <>
            <h2 className="text-h2 text-primary">Verification failed</h2>
            <Alert variant="danger" className="mt-2">
              {message}
            </Alert>
            <p className="mt-4 text-body text-secondary">
              Enter your email to request a new link.
            </p>
            <ResendForm />
          </>
        )}
      </Card>
    </AuthLayout>
  )
}
