import createClient from "openapi-fetch";
import type { paths } from "./schema";

// baseUrl: same-origin in the browser; absolute because Node's fetch (used
// under Vitest) cannot parse a relative URL ("Failed to parse URL").
// fetch: resolved per call, because openapi-fetch otherwise captures
// globalThis.fetch at import time, before MSW patches it in tests.
export const api = createClient<paths>({
  baseUrl: globalThis.location.origin,
  fetch: (request) => globalThis.fetch(request),
});
