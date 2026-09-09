import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { StrictMode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { server } from '../../test/msw/server'
import { apiUrl } from '../../test/fixtures'
import { VerifyEmailPage } from '../VerifyEmailPage'

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <VerifyEmailPage />
    </MemoryRouter>,
  )
}

describe('VerifyEmailPage', () => {
  it('shows a success state with a link to /login when the token is valid', async () => {
    server.use(
      http.post(apiUrl('/auth/verify-email/'), () => new HttpResponse(null, { status: 200 })),
    )
    renderAt('/verify-email?token=good-token')

    expect(
      await screen.findByRole('heading', { name: 'You’re verified' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute(
      'href',
      '/login',
    )
  })

  it('shows the backend’s generic failure message for an invalid/expired token', async () => {
    server.use(
      http.post(apiUrl('/auth/verify-email/'), () =>
        HttpResponse.json(
          { detail: 'This verification link is invalid or has expired.' },
          { status: 400 },
        ),
      ),
    )
    renderAt('/verify-email?token=bad-token')

    expect(
      await screen.findByRole('heading', { name: 'Verification failed' }),
    ).toBeInTheDocument()
    expect(
      screen.getByText('This verification link is invalid or has expired.'),
    ).toBeInTheDocument()
  })

  it('treats a missing token as a failure without making a request', async () => {
    let calls = 0
    server.use(
      http.post(apiUrl('/auth/verify-email/'), () => {
        calls += 1
        return new HttpResponse(null, { status: 200 })
      }),
    )
    renderAt('/verify-email')

    expect(
      await screen.findByRole('heading', { name: 'Verification failed' }),
    ).toBeInTheDocument()
    expect(screen.getByText(/missing its token/i)).toBeInTheDocument()
    expect(calls).toBe(0)
  })

  it('can request a new link from the failure state', async () => {
    let resendBody: unknown = null
    server.use(
      http.post(apiUrl('/auth/verify-email/'), () =>
        HttpResponse.json({ detail: 'nope' }, { status: 400 }),
      ),
      http.post(apiUrl('/auth/resend-verification/'), async ({ request }) => {
        resendBody = await request.json()
        return HttpResponse.json({ detail: 'ok' })
      }),
    )
    renderAt('/verify-email?token=bad-token')
    await screen.findByRole('heading', { name: 'Verification failed' })

    await userEvent.type(screen.getByLabelText('Email'), 'retry@example.com')
    await userEvent.click(screen.getByRole('button', { name: 'Send a new link' }))

    expect(
      await screen.findByText(/we’ve sent a new verification link/i),
    ).toBeInTheDocument()
    expect(resendBody).toEqual({ email: 'retry@example.com' })
  })

  it('fires exactly one verify-email request even under StrictMode double-invoke', async () => {
    // Regression: a plain useEffect with no ref guard fired this POST twice
    // under StrictMode's mount→unmount→remount — harmless for an idempotent
    // call, but this token is single-use, so the second request always got
    // "already used" and showed a false failure for a verification that had
    // actually just succeeded on the first request. Same bug class as
    // AuthProvider's bootstrap effect (auth-context.test.tsx), worse
    // consequence here because the action isn't safe to repeat.
    let calls = 0
    server.use(
      http.post(apiUrl('/auth/verify-email/'), () => {
        calls += 1
        return calls === 1
          ? new HttpResponse(null, { status: 200 })
          : HttpResponse.json({ detail: 'already used' }, { status: 400 })
      }),
    )

    render(
      <StrictMode>
        <MemoryRouter initialEntries={['/verify-email?token=good-token']}>
          <VerifyEmailPage />
        </MemoryRouter>
      </StrictMode>,
    )

    expect(
      await screen.findByRole('heading', { name: 'You’re verified' }),
    ).toBeInTheDocument()
    expect(calls).toBe(1)
  })
})
