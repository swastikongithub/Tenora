import { QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'

import { AuthProvider } from './lib/auth'
import { ThemeProvider } from './lib/theme'
import { queryClient } from './lib/query-client'
import { AppRoutes } from './routes/AppRoutes'

/**
 * Provider stack for the whole app:
 *   ThemeProvider       — light/dark token set + toggle (client-only UI pref)
 *   QueryClientProvider — server-state cache (tenant isolation lives in the
 *                         query keys, see src/lib/query-keys.ts)
 *   AuthProvider        — silent-refresh-on-load, login/logout
 *   BrowserRouter       — routing; ProtectedRoute + AppShell hang off AppRoutes
 */
export function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <BrowserRouter>
            <AppRoutes />
          </BrowserRouter>
        </AuthProvider>
      </QueryClientProvider>
    </ThemeProvider>
  )
}
