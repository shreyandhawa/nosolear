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
