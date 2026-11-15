import { act, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { renderHookWithProviders } from "../../test/render";
import { server } from "../../test/server";
import { useSetup } from "./useSetup";

const row = (component: string, status: string, fix: string | null) => ({
  component,
  label: component,
  status,
  reason: "test",
  fix,
});

test("setup lists the missing .env lines and the check moves onboarding on", async () => {
  let probed = false;
  server.use(
    http.get("/api/readiness", () =>
      HttpResponse.json({
        ready: probed,
        rows: [
          row("azure_speech", "ready", null),
          row("anthropic", "missing", "set NOSOLEAR_ANTHROPIC_API_KEY in .env"),
          row("azure_capabilities", probed ? "ready" : "not_probed", "run the check"),
        ],
      }),
    ),
    http.get("/api/onboarding", () =>
      HttpResponse.json({
        step: probed ? "calibration" : "readiness",
        blockers: [],
        calibration: "not_run",
        baseline: "not_started",
        baseline_session_id: null,
      }),
    ),
    http.post("/api/readiness/probe", () => {
      probed = true;
      return HttpResponse.json({ outcomes: [{ adapter: "azure_pa", ok: true, message: "nbest_phonemes True" }] });
    }),
  );
  const { result } = renderHookWithProviders(useSetup);
  await waitFor(() => expect(result.current.envLines).toEqual(["NOSOLEAR_ANTHROPIC_API_KEY="]));
  expect(result.current.blocked).toBe(true);
  act(() => result.current.probe.mutate());
  await waitFor(() => expect(result.current.blocked).toBe(false));
  expect(result.current.probe.data?.outcomes[0].ok).toBe(true);
});
