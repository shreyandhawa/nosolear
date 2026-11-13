import type { Plugin } from "vite";

const LOOPBACK_HOSTS = new Set<unknown>([undefined, "localhost", "127.0.0.1", "::1"]);

/** Fails the dev server start when it would listen beyond this machine (spec section 10). */
export function loopbackOnly(): Plugin {
  return {
    name: "nosolear:loopback-only",
    configResolved(config) {
      const host = config.server.host;
      if (!LOOPBACK_HOSTS.has(host)) {
        throw new Error(
          `Refusing to serve on host ${String(host)}: the dev proxy gives anyone who can reach ` +
            "this server access to the unauthenticated API. Run it without --host. " +
            "See the Security section of the README.",
        );
      }
    },
  };
}
