import { QueryClient } from '@tanstack/react-query'

/**
 * Factory so tests can spin up an isolated client. The app uses the singleton
 * below.
 *
 * `retry: false` — the API client already does the one refresh-and-retry that
 * matters (a 401); a generic retry on top would just delay real errors and
 * replay a failed mutation-shaped GET. `refetchOnWindowFocus: false` — this is
 * an internal tool, not a live dashboard; background refetches on every
 * alt-tab are noise.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        refetchOnWindowFocus: false,
        staleTime: 30_000,
      },
      mutations: {
        retry: false,
      },
    },
  })
}

export const queryClient = createQueryClient()
