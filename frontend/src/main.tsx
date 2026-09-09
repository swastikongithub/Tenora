import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

// Geist + Geist Mono, bundled with the app (no font CDN <link>). Sans: 400/500/
// 600 are the only weights §C.1's type scale uses. Mono (IDs, slugs, keys) only
// ever renders at 400, and only over backend-validated latin slugs — so the
// `latin-` subset file, not the full one (which also carries cyrillic /
// vietnamese / symbols faces this app never renders). Swapped from Inter in the
// typography addendum — a token-level change, Geist's metrics are close enough
// to Inter's that no layout moved.
import '@fontsource/geist-sans/400.css'
import '@fontsource/geist-sans/500.css'
import '@fontsource/geist-sans/600.css'
import '@fontsource/geist-mono/latin-400.css'

import './styles/theme.css'
import { App } from './App'

const rootEl = document.getElementById('root')
if (!rootEl) throw new Error('Root element #root not found')

createRoot(rootEl).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
