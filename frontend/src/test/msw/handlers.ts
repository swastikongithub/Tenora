import type { RequestHandler } from 'msw'

/**
 * No default handlers. Every test declares exactly the endpoints it exercises
 * via `server.use(...)`, so a test can never accidentally pass against a stub it
 * forgot it had. The server runs with `onUnhandledRequest: 'bypass'` (see
 * src/test/setup.ts) so the existing component tests, which make no requests,
 * are unaffected.
 */
export const handlers: RequestHandler[] = []
