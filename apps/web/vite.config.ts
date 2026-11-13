import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

import { loopbackOnly } from "./vite-plugins/loopbackOnly.ts";

export default defineConfig({
  plugins: [loopbackOnly(), react(), tailwindcss()],
  server: {
    host: "localhost",
    strictPort: true,
    // changeOrigin stays false: the proxy must forward the browser's Host (localhost:5173),
    // which the API's host guard accepts.
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: false } },
  },
  // `vite preview` inherits the proxy above, so it gets the same pinning.
  preview: { host: "localhost", strictPort: true },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["src/test/setup.ts"],
  },
});
