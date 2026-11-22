import { act, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { onboarding, probeRun, readiness } from "../../test/fixtures";
import { renderHookWithProviders } from "../../test/render";
import { server } from "../../test/server";
import { useSetup } from "./useSetup";

test("the missing coach key is optional: it lists its .env line and never blocks", async () => {
  server.use(
    http.get("/api/readiness", () => HttpResponse.json(readiness(true))),
    http.get("/api/onboarding", () => HttpResponse.json(onboarding("calibration"))),
  );
  const { result } = renderHookWithProviders(useSetup);
  await waitFor(() => expect(result.current.coachLines).toEqual(["NOSOLEAR_ANTHROPIC_API_KEY="]));
  expect(result.current.envLines).toEqual([]);
  expect(result.current.blocked).toBe(false);
});

test("a missing Azure key is required: its lines are listed and the check moves onboarding on", async () => {
  let probed = false;
  const azureMissing = () => {
    const r = readiness(probed);
    r.rows[0] = {
      ...r.rows[0],
      status: probed ? "ready" : "missing",
      fix: probed ? null : "set NOSOLEAR_AZURE_SPEECH_KEY and NOSOLEAR_AZURE_SPEECH_REGION in .env",
    };
    return r;
  };
  server.use(
    http.get("/api/readiness", () => HttpResponse.json(azureMissing())),
    http.get("/api/onboarding", () => HttpResponse.json(onboarding(probed ? "calibration" : "readiness"))),
    http.post("/api/readiness/probe", () => {
      probed = true;
      return HttpResponse.json(probeRun);
    }),
  );
  const { result } = renderHookWithProviders(useSetup);
  await waitFor(() =>
    expect(result.current.envLines).toEqual(["NOSOLEAR_AZURE_SPEECH_KEY=", "NOSOLEAR_AZURE_SPEECH_REGION="]),
  );
  expect(result.current.blocked).toBe(true);
  act(() => result.current.probe.mutate());
  await waitFor(() => expect(result.current.blocked).toBe(false));
  expect(result.current.probe.data?.outcomes[0].ok).toBe(true);
});
