/// <reference types="vitest/config" />
import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Shared constants from docs/P0-work-packages.md: dev port 5173, backend port 7880 (lead override).
const DEV_PORT = 5173;
const BACKEND_ORIGIN = "http://127.0.0.1:7880";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  server: {
    host: "127.0.0.1",
    port: DEV_PORT,
    proxy: { "/api": { target: BACKEND_ORIGIN, changeOrigin: false } },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
