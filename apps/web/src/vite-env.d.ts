/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  /**
   * Build-time local development token. Never read from the URL, localStorage
   * or user input, and never bake a real token into a public production build.
   */
  readonly VITE_API_TOKEN?: string;
  /**
   * When "true", mock/demo deposits also generate circuit-compatible Poseidon
   * note v2. Local Anvil mode always uses note v2. No prover is wired yet.
   */
  readonly VITE_ZK_NOTES?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
