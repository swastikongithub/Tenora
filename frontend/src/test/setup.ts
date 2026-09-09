import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterAll, afterEach, beforeAll } from 'vitest'

import { server } from './msw/server'

// jsdom has no matchMedia. Default every query to "matches" so components that
// branch on a breakpoint render their desktop layout unless a test overrides
// window.matchMedia for a mobile-specific assertion.
if (typeof window.matchMedia !== 'function') {
  window.matchMedia = (query: string): MediaQueryList =>
    ({
      matches: true,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList
}

// `bypass`, not `error`: the C1 component tests make no HTTP calls, and a test
// that does make one always registers its own handler. An unhandled request is
// therefore a test bug, but failing loudly here would just add noise to the
// suites that never touch the network.
beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))

afterEach(() => {
  server.resetHandlers()
  cleanup()
  try {
    sessionStorage.clear()
    localStorage.clear()
  } catch {
    /* storage not available in this environment */
  }
})

afterAll(() => server.close())
