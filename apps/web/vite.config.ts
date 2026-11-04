import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // The prover worker dynamically imports snarkjs, which needs a code-split
  // ES-module worker rather than Vite's default IIFE output.
  worker: {
    format: "es",
  },
  server: {
    port: 5173,
    host: "127.0.0.1",
  },
  preview: {
    port: 4173,
    host: "127.0.0.1",
  },
});
