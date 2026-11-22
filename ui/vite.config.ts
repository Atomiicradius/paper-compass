/// <reference types="vitest/config" />
import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The UI talks to the FastAPI backend over HTTP only. In development the browser calls /api/... on the Vite
// server, which forwards it to the API (default http://127.0.0.1:8000), so the API needs no CORS settings.
const apiTarget = process.env.PC_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  server: {
    port: 5173,
    proxy: { "/api": { target: apiTarget, changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, ""), timeout: 600_000, proxyTimeout: 600_000 } },
  },
  preview: { port: 4173, proxy: { "/api": { target: apiTarget, changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, "") } } },
  test: { environment: "jsdom", setupFiles: ["./src/test/setup.ts"], globals: true, css: false },
});
