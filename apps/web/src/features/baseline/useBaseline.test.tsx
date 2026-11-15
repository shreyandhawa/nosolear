import { act, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { renderHookWithProviders } from "../../test/render";
import { server } from "../../test/server";
import { useBaseline } from "./useBaseline";

const session = (completed: boolean) => ({
  session_id: "b1",
  protocol_version: 1,
  started_at: "2026-11-15T10:00:00Z",
  completed_at: completed ? "2026-11-15T10:20:00Z" : null,
  items: [
    { attempt_id: "a1", item_id: "p1", order: 1, section: "Read aloud", step: "read", text: "A very good day.", scripted: true, max_seconds: 30, start_limit_seconds: null, stand_in_text: "A very good day.", recorded: true, job_status: "done" },
  ],
});

const report = {
  session_id: "b1",
  completed_at: "2026-11-15T10:20:00Z",
  calibration: "done",
  scoring_config_id: "c1",
  snapshot_id: "x1",
  notes: [],
  skill_scores: [{ skill: "sounds", score: 72, scores: {}, values: {} }],
  items: [
    { error_key: "sound.sub.v.w", description: "/v/ said as /w/", skill: "sounds", impact: 3, status: "active", p_hat: 0.3, ci_low: 0.1, ci_high: 0.5, n_eff: 4, priority: 0.9, provisional: true, clips: [{ attempt_id: "a1", start_ms: 100, end_ms: 400, word: "very", expected: "v", produced: "w" }] },
  ],
};

test("the baseline starts, completes and shows the ranked report", async () => {
  let current: object | null = null;
  server.use(
    http.get("/api/baseline", () =>
      current ? HttpResponse.json(current) : HttpResponse.json({ code: "no_baseline", message: "none" }, { status: 404 }),
    ),
    http.post("/api/baseline", () => {
      current = session(false);
      return HttpResponse.json(current);
    }),
    http.post("/api/baseline/complete", () => {
      current = session(true);
      return HttpResponse.json(report);
    }),
    http.get("/api/baseline/report", () => HttpResponse.json(report)),
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
