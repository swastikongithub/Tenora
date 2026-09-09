/// <reference types="vite/client" />

interface ImportMetaEnv {
  /**
   * Base URL every API request is prefixed with. Defaults to `/api`, which the
   * Vite dev server proxies to Django (see vite.config.ts). Never hardcode the
   * backend origin in source — Stage C2 spec §4.1.
   */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
