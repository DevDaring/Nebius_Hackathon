/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

// All API calls in the app are relative (/api/...). In dev and preview, Vite proxies /api to
// VITE_API_TARGET (default http://localhost:8000). In production, Caddy reverse-proxies /api.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.VITE_API_TARGET || process.env.VITE_API_TARGET || "http://localhost:8000";
  const proxy = { "/api": { target, changeOrigin: true } };
  // Dev and preview servers listen on loopback only. Opt in to LAN access with VITE_HOST=0.0.0.0.
  const host = env.VITE_HOST || process.env.VITE_HOST || "127.0.0.1";
  return {
    plugins: [react()],
    resolve: {
      alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
    },
    server: { port: 5180, strictPort: true, host, proxy },
    preview: { port: 5180, strictPort: true, host, proxy },
    // Main chunk is ~370 kB (locales, the home page, chart code and overlays are split out); warn if it regrows.
    build: { chunkSizeWarningLimit: 400 },
    test: {
      environment: "jsdom",
      globals: false,
      include: ["src/**/*.test.{ts,tsx}"],
    },
  };
});
