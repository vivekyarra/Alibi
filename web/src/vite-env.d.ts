/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string;
  readonly VITE_DOCS_BASE_URL?: string;
  readonly VITE_LIVE_ZONE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
