import { waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { onboarding } from "../../test/fixtures";
import { renderHookWithProviders } from "../../test/render";
import { server } from "../../test/server";
import { useHomeTarget } from "./useHomeTarget";

test("home goes to the screen for the onboarding step", async () => {
  server.use(http.get("/api/onboarding", () => HttpResponse.json(onboarding("calibration"))));
  const { result } = renderHookWithProviders(useHomeTarget);
  await waitFor(() => expect(result.current.target).toBe("/calibration"));
});
