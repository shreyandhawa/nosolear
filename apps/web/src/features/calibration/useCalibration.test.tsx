import { act, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { renderHookWithProviders } from "../../test/render";
import { server } from "../../test/server";
import { useCalibration } from "./useCalibration";

const item = (order: number, recorded: boolean) => ({
  attempt_id: `a${order}`,
  item_id: `w${order}`,
  order,
  error_key: "sound.sub.v.w",
  word: "very",
  deliberate: order === 2,
  take: 1,
  instruction: "Say it as you usually would.",
  stand_in_text: "very",
  recorded,
  job_status: recorded ? "done" : null,
});

const run = (status: string, recorded: boolean[]) => ({
  run_id: "r1",
  session_id: "s1",
  status,
  scoring_config_id: null,
  started_at: "2026-11-15T10:00:00Z",
  completed_at: null,
  items: recorded.map((r, n) => item(n + 1, r)),
  results:
    status === "done"
      ? [{ detector: "azure_pa", error_key: "sound.sub.v.w", errors: 1, hits: 1, controls: 1, false_alarms: 0, correct_takes: 1, correct_flags: 0, covered: true, enabled: true, hit_rate: 1, false_alarm_rate: 0, correct_take_flag_rate: 0, warning: null }]
      : [],
});

test("calibration starts, resumes at the first unrecorded take, finishes and shows the result", async () => {
  let current: object | null = null;
  server.use(
    http.get("/api/calibration", () =>
      current ? HttpResponse.json(current) : HttpResponse.json({ code: "no_calibration", message: "none" }, { status: 404 }),
    ),
    http.post("/api/calibration", () => {
      current = run("running", [true, false]);
      return HttpResponse.json(current);
    }),
    http.post("/api/calibration/finish", () => HttpResponse.json({ job_id: "j1" }, { status: 202 })),
    http.get("/api/jobs/j1", () => {
      current = run("done", [true, true]);
      return HttpResponse.json({ id: "j1", kind: "calibrate", attempt_id: null, status: "done", progress: 1, step: null, steps: [], tries: 1 });
    }),
    http.get("/api/onboarding", () => HttpResponse.json({})),
  );
  const { result } = renderHookWithProviders(useCalibration);
  await waitFor(() => expect(result.current.run.data).toBeNull());
  act(() => result.current.start.mutate());
  await waitFor(() => expect(result.current.current?.attempt_id).toBe("a2"));
  expect(result.current.position).toBe(2);
  act(() => result.current.finish.mutate());
  await waitFor(() => expect(result.current.run.data?.status).toBe("done"));
  expect(result.current.run.data?.results[0].enabled).toBe(true);
});
