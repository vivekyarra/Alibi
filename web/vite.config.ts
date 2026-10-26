import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// API base defaults to /v1. In dev, /v1 is proxied to the local API (SPEC 10.7).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/v1": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
    testTimeout: 60000,
  },
});
