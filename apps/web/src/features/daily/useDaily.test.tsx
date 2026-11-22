import { act, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { analyzeJob, completed, dailySession, feedback, plan } from "../../test/fixtures";
import { renderHookWithProviders } from "../../test/render";
import { server } from "../../test/server";
import { useDaily } from "./useDaily";

test("a daily session goes from plan to recording, analysis, feedback and complete", async () => {
  let feedbackPosts = 0;
  server.use(
    http.get("/api/plan/today", () => HttpResponse.json(plan)),
    http.post("/api/plan/today/session", () => HttpResponse.json(dailySession, { status: 201 })),
    http.get("/api/jobs/j1", () => HttpResponse.json(analyzeJob())),
    http.post("/api/sessions/s1/feedback", () => {
      feedbackPosts += 1;
      return HttpResponse.json(feedback);
    }),
    http.post("/api/sessions/s1/complete", () => HttpResponse.json(completed)),
  );
  const { result } = renderHookWithProviders(useDaily);
  await waitFor(() => expect(result.current.plan.data?.seed).toBe("18446744073709551615"));
  act(() => result.current.start.mutate());
  await waitFor(() => expect(result.current.state.phase).toBe("record"));
  act(() => result.current.uploaded("j1"));
  await waitFor(() => expect(result.current.state.phase).toBe("feedback"));
  expect(feedbackPosts).toBe(1);
  const state = result.current.state;
  expect(state.phase === "feedback" && state.feedback.skills.map((s) => s.state)).toEqual(["fix", "not_scored", "clean"]);
  act(() => result.current.complete.mutate("s1"));
  await waitFor(() => expect(result.current.state.phase).toBe("done"));
});

test("opening Today again resumes at analysis when the session already has a recording", async () => {
  server.use(
    http.get("/api/plan/today", () => HttpResponse.json(plan)),
    http.post("/api/plan/today/session", () => HttpResponse.json({ ...dailySession, job_id: "j1" })),
    http.get("/api/jobs/j1", () => HttpResponse.json(analyzeJob("running", 0.5))),
  );
  const { result } = renderHookWithProviders(useDaily);
  await waitFor(() => expect(result.current.state.phase).toBe("analyze"));
  expect(result.current.job?.status).toBe("running");
});

test("opening Today again after completion shows the stored feedback as done", async () => {
  server.use(
    http.get("/api/plan/today", () => HttpResponse.json(plan)),
    http.post("/api/plan/today/session", () => HttpResponse.json({ ...dailySession, job_id: "j1", completed: true })),
    http.get("/api/sessions/s1/feedback", () => HttpResponse.json(feedback)),
  );
  const { result } = renderHookWithProviders(useDaily);
  await waitFor(() => expect(result.current.state.phase).toBe("done"));
});
