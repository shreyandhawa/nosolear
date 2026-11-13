import type { ResolvedConfig } from "vite";
import { describe, expect, it } from "vitest";

import { loopbackOnly } from "./loopbackOnly.ts";

function resolve(host: unknown) {
  const plugin = loopbackOnly();
  const hook = plugin.configResolved as (config: ResolvedConfig) => void;
  return () => hook({ server: { host } } as unknown as ResolvedConfig);
}

describe("loopbackOnly", () => {
  it.each([undefined, "localhost", "127.0.0.1", "::1"])("allows host %s", (host) => {
    expect(resolve(host)).not.toThrow();
  });

  it.each([true, "0.0.0.0", "::", "192.168.1.10"])("refuses host %s", (host) => {
    expect(resolve(host)).toThrow(/Security/);
  });
});
