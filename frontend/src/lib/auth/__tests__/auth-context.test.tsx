import { StrictMode } from 'react'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'

import { server } from '../../../test/msw/server'
import {
  getCurrentTenantId,
  setCurrentTenantId,
} from '../../tenant/current-tenant'
import { AuthProvider } from '../AuthProvider'
import { useAuth } from '../auth-context'
import { endSession } from '../session'
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setRefreshToken,
} from '../token-store'

const api = (path: string) => `*/api${path}`

beforeEach(() => {
  clearTokens()
  setCurrentTenantId(null)
})

function Probe() {
  const { status, login, logout } = useAuth()
  return (
    <div>
      <output data-testid="status">{status}</output>
      <button onClick={() => void login('a@b.c', 'pw').catch(() => {})}>
        login
      </button>
      <button onClick={logout}>logout</button>
    </div>
  )
}

function renderProvider() {
  return render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  )
}

async function waitForStatus(value: string) {
  await waitFor(() =>
    expect(screen.getByTestId('status')).toHaveTextContent(value),
  )
}

describe('AuthProvider — load / bootstrap', () => {
  it('settles to unauthenticated when no refresh token is stored', async () => {
    renderProvider()
    await waitForStatus('unauthenticated')
  })

  it('silently re-authenticates on load with a valid refresh token', async () => {
    setRefreshToken('refresh-1')
    server.use(
      http.post(api('/auth/refresh/'), () =>
        HttpResponse.json({ access: 'access-2', refresh: 'refresh-2' }),
      ),
    )

    renderProvider()
    await waitForStatus('authenticated')
    expect(getAccessToken()).toBe('access-2')
    expect(getRefreshToken()).toBe('refresh-2') // rotation replaced it
  })

  it('reaches authenticated on a reload even under StrictMode double-invoke', async () => {
    // Regression: the bootstrap effect's cancelled-closure + ref guard left
    // status stuck on 'loading' when StrictMode mounts, unmounts, remounts —
    // i.e. on every authenticated dev reload (C3 discovery).
    setRefreshToken('refresh-1')
    server.use(
      http.post(api('/auth/refresh/'), () =>
        HttpResponse.json({ access: 'access-2', refresh: 'refresh-2' }),
      ),
    )

    render(
      <StrictMode>
        <AuthProvider>
          <Probe />
        </AuthProvider>
      </StrictMode>,
    )

    await waitForStatus('authenticated')
  })

  it('clears an invalid refresh token on load and stays unauthenticated', async () => {
    setRefreshToken('refresh-bad')
    server.use(
      http.post(
        api('/auth/refresh/'),
        () => new HttpResponse(null, { status: 401 }),
      ),
    )

    renderProvider()
    await waitForStatus('unauthenticated')
    expect(getRefreshToken()).toBeNull()
  })
})

describe('AuthProvider — login / logout', () => {
  it('login stores both tokens and becomes authenticated', async () => {
    server.use(
      http.post(api('/auth/login/'), () =>
        HttpResponse.json({ access: 'access-login', refresh: 'refresh-login' }),
      ),
    )

    renderProvider()
    await waitForStatus('unauthenticated')
    await userEvent.click(screen.getByText('login'))

    await waitForStatus('authenticated')
    expect(getAccessToken()).toBe('access-login')
    expect(sessionStorage.getItem('billing.refresh_token')).toBe(
      'refresh-login',
    )
  })

  it('a rejected login leaves the user unauthenticated with no tokens', async () => {
    server.use(
      http.post(api('/auth/login/'), () =>
        HttpResponse.json(
          { detail: 'No active account found with the given credentials' },
          { status: 401 },
        ),
      ),
    )

    renderProvider()
    await waitForStatus('unauthenticated')
    await userEvent.click(screen.getByText('login'))

    // Let the rejected login promise settle.
    await act(() => Promise.resolve())
    expect(screen.getByTestId('status')).toHaveTextContent('unauthenticated')
    expect(getAccessToken()).toBeNull()
    expect(getRefreshToken()).toBeNull()
  })

  it('logout clears tokens and tenant context', async () => {
    server.use(
      http.post(api('/auth/login/'), () =>
        HttpResponse.json({ access: 'a', refresh: 'r' }),
      ),
      // §4.6: logout() now also fires a best-effort blacklist call.
      http.post(api('/auth/logout/'), () => new HttpResponse(null, { status: 200 })),
    )

    renderProvider()
    await waitForStatus('unauthenticated')
    await userEvent.click(screen.getByText('login'))
    await waitForStatus('authenticated')

    setCurrentTenantId('tenant-1')
    await userEvent.click(screen.getByText('logout'))

    await waitForStatus('unauthenticated')
    expect(getAccessToken()).toBeNull()
    expect(getRefreshToken()).toBeNull()
    expect(getCurrentTenantId()).toBeNull()
  })

  it('an ended session (from the API client) flips status to unauthenticated', async () => {
    server.use(
      http.post(api('/auth/login/'), () =>
        HttpResponse.json({ access: 'a', refresh: 'r' }),
      ),
    )

    renderProvider()
    await waitForStatus('unauthenticated')
    await userEvent.click(screen.getByText('login'))
    await waitForStatus('authenticated')

    setCurrentTenantId('tenant-1')
    await act(() => {
      endSession()
    })

    expect(screen.getByTestId('status')).toHaveTextContent('unauthenticated')
    expect(getCurrentTenantId()).toBeNull()
  })
})
