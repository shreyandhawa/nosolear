import { describe, expect, it } from "vitest";

import config from "./vite.config";

describe("vite config", () => {
  const server = config.server!;
  const proxy = server.proxy as Record<string, { target: string; changeOrigin: boolean }>;

  it("keeps the browser's Host header on the /api proxy", () => {
    expect(proxy["/api"].changeOrigin).toBe(false);
    expect(proxy["/api"].target).toBe("http://127.0.0.1:8000");
  });

  it("pins the dev server to localhost", () => {
    expect(server.host).toBe("localhost");
    expect(server.strictPort).toBe(true);
    expect(server.allowedHosts).not.toBe(true);
  });
});
