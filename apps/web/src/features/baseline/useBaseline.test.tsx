import { act, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { baselineReport, baselineSession } from "../../test/fixtures";
import { renderHookWithProviders } from "../../test/render";
import { server } from "../../test/server";
import { useBaseline } from "./useBaseline";

test("the baseline starts, completes and shows the ranked report", async () => {
  let current: object | null = null;
  server.use(
    http.get("/api/baseline", () =>
      current ? HttpResponse.json(current) : HttpResponse.json({ code: "no_baseline", message: "none" }, { status: 404 }),
    ),
    http.post("/api/baseline", () => {
      current = baselineSession(false);
      return HttpResponse.json(current);
    }),
    http.post("/api/baseline/complete", () => {
      current = baselineSession(true);
      return HttpResponse.json(baselineReport);
    }),
    http.get("/api/baseline/report", () => HttpResponse.json(baselineReport)),
    http.get("/api/onboarding", () => HttpResponse.json({})),
  );
  const { result } = renderHookWithProviders(useBaseline);
  await waitFor(() => expect(result.current.session.data).toBeNull());
  act(() => result.current.start.mutate());
  await waitFor(() => expect(result.current.allRecorded).toBe(true));
  act(() => result.current.complete.mutate());
  await waitFor(() => expect(result.current.completed).toBe(true));
  expect(result.current.report?.items[0].provisional).toBe(true);
  expect(result.current.report?.skill_scores[0].score).toBe(72);
});
