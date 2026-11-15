import { waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { renderHookWithProviders } from "../../test/render";
import { server } from "../../test/server";
import { useHomeTarget } from "./useHomeTarget";

test("home goes to the screen for the onboarding step", async () => {
  server.use(
    http.get("/api/onboarding", () =>
      HttpResponse.json({ step: "calibration", blockers: [], calibration: "not_run", baseline: "not_started", baseline_session_id: null }),
    ),
  );
  const { result } = renderHookWithProviders(useHomeTarget);
  await waitFor(() => expect(result.current.target).toBe("/calibration"));
});
