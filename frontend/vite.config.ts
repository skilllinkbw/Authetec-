import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Dev server proxies API calls to the local Authetec backend so the UI
// and API share an origin in development (no CORS exposure of secrets).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/health": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
