import { act, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { onboarding, probeRun, readiness } from "../../test/fixtures";
import { renderHookWithProviders } from "../../test/render";
import { server } from "../../test/server";
import { useSetup } from "./useSetup";

test("setup lists the missing .env lines and the check moves onboarding on", async () => {
  let probed = false;
  server.use(
    http.get("/api/readiness", () => HttpResponse.json(readiness(probed))),
    http.get("/api/onboarding", () => HttpResponse.json(onboarding(probed ? "calibration" : "readiness"))),
    http.post("/api/readiness/probe", () => {
      probed = true;
      return HttpResponse.json(probeRun);
    }),
  );
  const { result } = renderHookWithProviders(useSetup);
  await waitFor(() => expect(result.current.envLines).toEqual(["NOSOLEAR_ANTHROPIC_API_KEY="]));
  expect(result.current.blocked).toBe(true);
  act(() => result.current.probe.mutate());
  await waitFor(() => expect(result.current.blocked).toBe(false));
  expect(result.current.probe.data?.outcomes[0].ok).toBe(true);
});
