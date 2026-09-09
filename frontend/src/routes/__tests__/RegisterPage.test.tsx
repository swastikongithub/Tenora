import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { server } from '../../test/msw/server'
import { apiUrl, authHandlers, TENANT_A, tenantsMeHandler } from '../../test/fixtures'
import { AuthProvider } from '../../lib/auth'
import { setCurrentTenantId } from '../../lib/tenant'
import { createQueryClient } from '../../lib/query-client'
import { AppRoutes } from '../AppRoutes'

vi.mock('../../lib/config', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/config')>()
  return { ...actual, GOOGLE_OAUTH_CLIENT_ID: 'test-client-id.apps.googleusercontent.com' }
})

/** Stubs window.google.accounts.id, capturing the callback GoogleSignInButton
 *  registers so a test can simulate the user completing the Google flow
 *  (spec §9/§11 — never a real OAuth interaction in tests). */
function stubGoogleIdentityServices() {
  let capturedCallback: ((response: { credential: string }) => void) | null = null
  const w = window as unknown as {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            callback: (response: { credential: string }) => void
          }) => void
          renderButton: () => void
        }
      }
    }
  }
  w.google = {
    accounts: {
      id: {
        initialize: (config) => {
          capturedCallback = config.callback
        },
        renderButton: () => {},
      },
    },
  }
  return {
    fireCredentialResponse: (credential: string) => {
      if (!capturedCallback) throw new Error('initialize() was never called')
      capturedCallback({ credential })
    },
  }
}

function renderAt(path: string) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <MemoryRouter initialEntries={[path]}>
          <AppRoutes />
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  )
}

const registerOk = () =>
  http.post(apiUrl('/auth/register/'), () =>
    HttpResponse.json({ id: 'u1', email: 'new@example.com' }, { status: 201 }),
  )

async function fill({
  email = 'new@example.com',
  password = 'correct-horse-staple-42',
  confirm = password,
}: {
  email?: string
  password?: string
  confirm?: string
} = {}) {
  await userEvent.type(screen.getByLabelText('Email'), email)
  await userEvent.type(screen.getByLabelText('Password'), password)
  await userEvent.type(screen.getByLabelText('Confirm password'), confirm)
  await userEvent.click(
    screen.getByRole('button', { name: 'Create account' }),
  )
}

beforeEach(() => {
  setCurrentTenantId(null)
  delete (window as { google?: unknown }).google
})

describe('RegisterPage', () => {
  it('renders the form with new-password autocomplete hints', async () => {
    renderAt('/register')
    expect(
      await screen.findByRole('heading', { name: 'Create account' }),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toHaveAttribute(
      'autocomplete',
      'new-password',
    )
  })

  it('catches a password-confirmation mismatch before any request', async () => {
    let registerCalls = 0
    server.use(
      http.post(apiUrl('/auth/register/'), () => {
        registerCalls += 1
        return HttpResponse.json({ id: 'u1', email: 'new@example.com' }, { status: 201 })
      }),
    )
    renderAt('/register')
    await screen.findByRole('heading', { name: 'Create account' })

    await fill({ password: 'correct-horse-staple-42', confirm: 'different-thing-99' })

    expect(
      await screen.findByText('Passwords do not match.'),
    ).toBeInTheDocument()
    expect(registerCalls).toBe(0)
  })

  it('renders the backend field error for a duplicate email inline', async () => {
    server.use(
      http.post(apiUrl('/auth/register/'), () =>
        HttpResponse.json(
          { email: ['A user with this email already exists.'] },
          { status: 400 },
        ),
      ),
    )
    renderAt('/register')
    await screen.findByRole('heading', { name: 'Create account' })

    await fill()

    expect(
      await screen.findByText('A user with this email already exists.'),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('Email')).toHaveAttribute('aria-invalid', 'true')
  })

  it('renders the backend field error for a weak password inline', async () => {
    server.use(
      http.post(apiUrl('/auth/register/'), () =>
        HttpResponse.json(
          { password: ['This password is too short.'] },
          { status: 400 },
        ),
      ),
    )
    renderAt('/register')
    await screen.findByRole('heading', { name: 'Create account' })

    await fill()

    expect(
      await screen.findByText('This password is too short.'),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toHaveAttribute(
      'aria-invalid',
      'true',
    )
  })

  it('registers and shows a "check your email" confirmation, with no auto-login', async () => {
    let loginCalls = 0
    server.use(
      registerOk(),
      http.post(apiUrl('/auth/login/'), () => {
        loginCalls += 1
        return HttpResponse.json({ access: 'x', refresh: 'y' })
      }),
    )
    renderAt('/register')
    await screen.findByRole('heading', { name: 'Create account' })

    await fill({ email: 'new@example.com' })

    expect(
      await screen.findByRole('heading', { name: 'Check your email' }),
    ).toBeInTheDocument()
    expect(screen.getByText('new@example.com')).toBeInTheDocument()
    // §4.8: no auto-login attempt at all — the account isn't usable yet.
    expect(loginCalls).toBe(0)
  })

  it('does not navigate away from the confirmation screen', async () => {
    server.use(registerOk())
    renderAt('/register')
    await screen.findByRole('heading', { name: 'Create account' })

    await fill()

    await screen.findByRole('heading', { name: 'Check your email' })
    expect(
      screen.queryByRole('heading', { name: 'Workspaces' }),
    ).not.toBeInTheDocument()
  })

  it('can trigger resend-verification from the confirmation screen', async () => {
    let resendCalls = 0
    let resendBody: unknown = null
    server.use(
      registerOk(),
      http.post(apiUrl('/auth/resend-verification/'), async ({ request }) => {
        resendCalls += 1
        resendBody = await request.json()
        return HttpResponse.json({ detail: 'ok' })
      }),
    )
    renderAt('/register')
    await screen.findByRole('heading', { name: 'Create account' })

    await fill({ email: 'new@example.com' })
    await screen.findByRole('heading', { name: 'Check your email' })

    await userEvent.click(screen.getByRole('button', { name: 'Resend email' }))

    expect(
      await screen.findByText(/another verification email has been sent/i),
    ).toBeInTheDocument()
    expect(resendCalls).toBe(1)
    expect(resendBody).toEqual({ email: 'new@example.com' })
  })

  it('surfaces a generic failure on register inline, never a stuck spinner', async () => {
    server.use(
      http.post(apiUrl('/auth/register/'), () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    )
    renderAt('/register')
    await screen.findByRole('heading', { name: 'Create account' })

    await fill()

    expect(
      await screen.findByText(
        'The server had a problem handling that. Try again in a moment.',
      ),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Create account' }),
    ).not.toHaveAttribute('aria-busy')
  })

  it('renders a Google sign-in option and a successful callback lands in the app', async () => {
    server.use(
      http.post(apiUrl('/auth/google/'), () =>
        HttpResponse.json({ access: 'a', refresh: 'r' }),
      ),
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
    )
    const google = stubGoogleIdentityServices()
    renderAt('/register')
    await screen.findByRole('heading', { name: 'Create account' })

    google.fireCredentialResponse('fake-google-jwt')

    // isAuthenticated flips true → RegisterPage's own <Navigate> redirects,
    // same as LoginPage's imperative navigate() does for password login.
    expect(
      await screen.findByRole('heading', { name: 'Workspaces' }),
    ).toBeInTheDocument()
  })
})
