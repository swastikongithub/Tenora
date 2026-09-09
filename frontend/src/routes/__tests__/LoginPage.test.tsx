import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { server } from '../../test/msw/server'
import {
  authHandlers,
  apiUrl,
  TENANT_A,
  tenantsMeHandler,
} from '../../test/fixtures'
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

async function fillAndSubmit() {
  await userEvent.type(screen.getByLabelText('Email'), 'user@example.com')
  await userEvent.type(screen.getByLabelText('Password'), 'correct horse')
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
}

beforeEach(() => {
  setCurrentTenantId(null)
  delete (window as { google?: unknown }).google
})

describe('LoginPage', () => {
  it('renders a real form', async () => {
    renderAt('/login')
    expect(
      await screen.findByRole('heading', { name: 'Sign in' }),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('Email')).toHaveAttribute(
      'autocomplete',
      'username',
    )
    expect(screen.getByLabelText('Password')).toHaveAttribute(
      'autocomplete',
      'current-password',
    )
  })

  it('links to the register page', async () => {
    renderAt('/login')
    await screen.findByRole('heading', { name: 'Sign in' })

    await userEvent.click(screen.getByRole('link', { name: 'Create account' }))

    expect(
      await screen.findByRole('heading', { name: 'Create account' }),
    ).toBeInTheDocument()
  })

  it('signs in and lands on workspace selection on success', async () => {
    server.use(...authHandlers(), tenantsMeHandler([TENANT_A]))
    renderAt('/login')
    await screen.findByRole('heading', { name: 'Sign in' })

    await fillAndSubmit()

    // §C.4 Page 1: success → workspace selection, not straight to the shell.
    expect(
      await screen.findByRole('heading', { name: 'Workspaces' }),
    ).toBeInTheDocument()
  })

  it('shows ONE generic message on a 401 and stays on the login page', async () => {
    server.use(
      http.post(apiUrl('/auth/login/'), () =>
        HttpResponse.json(
          { detail: 'No active account found with the given credentials' },
          { status: 401 },
        ),
      ),
    )
    renderAt('/login')
    await screen.findByRole('heading', { name: 'Sign in' })

    await fillAndSubmit()

    expect(
      await screen.findByText('Email or password is incorrect.'),
    ).toBeInTheDocument()
    // The backend's "no active account" wording must not leak through.
    expect(screen.queryByText(/no active account/i)).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('shows a distinct retryable message on a transport failure', async () => {
    server.use(http.post(apiUrl('/auth/login/'), () => HttpResponse.error()))
    renderAt('/login')
    await screen.findByRole('heading', { name: 'Sign in' })

    await fillAndSubmit()

    expect(
      await screen.findByText(/Couldn’t reach the server/),
    ).toBeInTheDocument()
    expect(
      screen.queryByText('Email or password is incorrect.'),
    ).not.toBeInTheDocument()
  })

  it('redirects to workspace selection when already authenticated', async () => {
    sessionStorage.setItem('billing.refresh_token', 'valid-refresh')
    server.use(...authHandlers(), tenantsMeHandler([TENANT_A]))

    renderAt('/login')

    expect(
      await screen.findByRole('heading', { name: 'Workspaces' }),
    ).toBeInTheDocument()
  })

  it('renders a Google sign-in option and a successful callback lands on workspace selection', async () => {
    server.use(
      http.post(apiUrl('/auth/google/'), () =>
        HttpResponse.json({ access: 'a', refresh: 'r' }),
      ),
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
    )
    const google = stubGoogleIdentityServices()
    renderAt('/login')
    await screen.findByRole('heading', { name: 'Sign in' })

    google.fireCredentialResponse('fake-google-jwt')

    expect(
      await screen.findByRole('heading', { name: 'Workspaces' }),
    ).toBeInTheDocument()
  })
})
