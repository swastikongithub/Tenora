import { setupServer } from 'msw/node'

import { handlers } from './handlers'

/**
 * Node-side MSW server: intercepts `fetch` at the network layer so the API
 * client and auth flow run against real HTTP semantics (status codes, headers,
 * bodies) with no live Django — Stage C2 spec §10.
 */
export const server = setupServer(...handlers)
