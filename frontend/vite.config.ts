import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // Dev-only: route /api/* to Django so the browser makes same-origin
      // requests and no CORS config is needed on the backend (Stage C2 spec
      // §4.7 — do NOT add django-cors-headers). Production CORS is a later
      // (Docker) stage. Override the target via a normal Vite env if Django
      // runs elsewhere.
      '/api': {
        target: process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
    css: true,
  },
})
