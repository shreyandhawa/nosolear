import { act, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { calibrateJob, calibrationRun } from "../../test/fixtures";
import { renderHookWithProviders } from "../../test/render";
import { server } from "../../test/server";
import { useCalibration } from "./useCalibration";

test("calibration starts, resumes at the first unrecorded take, finishes and shows the result", async () => {
  let current: object | null = null;
  server.use(
    http.get("/api/calibration", () =>
      current ? HttpResponse.json(current) : HttpResponse.json({ code: "no_calibration", message: "none" }, { status: 404 }),
    ),
    http.post("/api/calibration", () => {
      current = calibrationRun("running", [true, false]);
      return HttpResponse.json(current);
    }),
    http.post("/api/calibration/finish", () => HttpResponse.json({ job_id: "j1" }, { status: 202 })),
    http.get("/api/jobs/j1", () => {
      current = calibrationRun("done", [true, true]);
      return HttpResponse.json(calibrateJob);
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
