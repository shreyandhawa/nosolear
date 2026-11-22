import { waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { onboarding } from "../../test/fixtures";
import { renderHookWithProviders } from "../../test/render";
import { server } from "../../test/server";
import { markWelcomeSeen } from "../../shared/welcomeSeen";
import { useHomeTarget } from "./useHomeTarget";

beforeEach(() => localStorage.clear());

test("home goes to the screen for the onboarding step", async () => {
  server.use(http.get("/api/onboarding", () => HttpResponse.json(onboarding("calibration"))));
  const { result } = renderHookWithProviders(useHomeTarget);
  await waitFor(() => expect(result.current.target).toBe("/calibration"));
});

test("a first visit goes to Welcome, then to setup once it has been seen", async () => {
  server.use(http.get("/api/onboarding", () => HttpResponse.json(onboarding("readiness"))));
  const first = renderHookWithProviders(useHomeTarget);
  await waitFor(() => expect(first.result.current.target).toBe("/welcome"));
  markWelcomeSeen();
  const later = renderHookWithProviders(useHomeTarget);
  await waitFor(() => expect(later.result.current.target).toBe("/setup"));
});
