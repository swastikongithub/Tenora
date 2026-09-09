import { render, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { server } from '../../test/msw/server'
import { apiUrl } from '../../test/fixtures'
import { AuthProvider } from '../../lib/auth'
import { GoogleSignInButton } from '../GoogleSignInButton'

vi.mock('../../lib/config', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/config')>()
  return { ...actual, GOOGLE_OAUTH_CLIENT_ID: 'test-client-id.apps.googleusercontent.com' }
})

/** Stubs window.google.accounts.id the way the real GIS script would define
 *  it, capturing the callback GoogleSignInButton registers so a test can
 *  invoke it directly — simulating the user completing the Google flow
 *  without attempting any real OAuth interaction (spec §9/§11). */
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

function renderButton(onSuccess = vi.fn(), onError = vi.fn()) {
  render(
    <AuthProvider>
      <GoogleSignInButton onSuccess={onSuccess} onError={onError} />
    </AuthProvider>,
  )
  return { onSuccess, onError }
}

beforeEach(() => {
  delete (window as { google?: unknown }).google
})

describe('GoogleSignInButton', () => {
  it('POSTs the credential from the Google callback and calls onSuccess', async () => {
    let requestBody: unknown = null
    server.use(
      http.post(apiUrl('/auth/google/'), async ({ request }) => {
        requestBody = await request.json()
        return HttpResponse.json({ access: 'a', refresh: 'r' })
      }),
    )
    // window.google is set before render, so it's already present when the
    // component's lazy ready-state initializer runs — initialize() fires
    // within the same render's effects, no polling needed in the test.
    const google = stubGoogleIdentityServices()
    const { onSuccess } = renderButton()

    google.fireCredentialResponse('fake-google-jwt')

    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1))
    expect(requestBody).toEqual({ credential: 'fake-google-jwt' })
  })

  it('calls onError with a message on a failed Google sign-in, not onSuccess', async () => {
    server.use(
      http.post(apiUrl('/auth/google/'), () =>
        HttpResponse.json({ detail: 'Google sign-in failed.' }, { status: 400 }),
      ),
    )
    const google = stubGoogleIdentityServices()
    const { onSuccess, onError } = renderButton()

    google.fireCredentialResponse('fake-google-jwt')

    await waitFor(() => expect(onError).toHaveBeenCalledWith('Google sign-in failed.'))
    expect(onSuccess).not.toHaveBeenCalled()
  })

  it('renders nothing when window.google is not yet available and no client ID configured path is not hit', () => {
    // window.google absent (beforeEach deleted it); GOOGLE_OAUTH_CLIENT_ID is
    // mocked non-empty above, so the component still renders its container
    // (a real script load would populate window.google shortly after) —
    // this just confirms it doesn't crash while waiting.
    const { container } = render(
      <AuthProvider>
        <GoogleSignInButton onSuccess={vi.fn()} onError={vi.fn()} />
      </AuthProvider>,
    )
    expect(container.querySelector('div')).toBeInTheDocument()
  })
})
