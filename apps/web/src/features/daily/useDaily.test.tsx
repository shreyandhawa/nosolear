import { act, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { renderHookWithProviders } from "../../test/render";
import { server } from "../../test/server";
import { useDaily } from "./useDaily";

const feedback = {
  session_id: "s1",
  degraded: true,
  skills: [
    {
      skill: "sounds",
      state: "fix",
      item: { id: "f1", error_key: "sound.sub.v.w", message: "Teeth on lip.", model_text: "very", source: "template", fallback_reason: "cap_exceeded", attempt_id: "a1", start_ms: 100, end_ms: 300, word: "very" },
    },
    { skill: "on_the_spot", state: "not_scored", item: null },
    { skill: "articulate", state: "clean", item: null },
  ],
};

test("a daily session goes from plan to recording, analysis, feedback and complete", async () => {
  let feedbackPosts = 0;
  server.use(
    http.get("/api/plan/today", () =>
      HttpResponse.json({ id: "p1", for_date: "2026-11-15", seed: "18446744073709551615", protocol_version: 1, foci: [], probe: null, prompt: { id: "q1", text: "Describe your morning.", target_keys: [] }, drills: [], steps: [] }),
    ),
    http.post("/api/plan/today/session", () =>
      HttpResponse.json({ session_id: "s1", plan_id: "p1", attempts: [{ id: "a1", step: "speak", prompt_text: "Describe your morning." }] }, { status: 201 }),
    ),
    http.get("/api/jobs/j1", () =>
      HttpResponse.json({ id: "j1", kind: "analyze", attempt_id: "a1", status: "done", progress: 1, step: null, steps: [{ name: "score", state: "done", error_code: null, message: null }], tries: 1 }),
    ),
    http.post("/api/sessions/s1/feedback", () => {
      feedbackPosts += 1;
      return HttpResponse.json(feedback);
    }),
    http.post("/api/sessions/s1/complete", () =>
      HttpResponse.json({ session_id: "s1", completed_at: "2026-11-15T10:10:00Z", already_completed: false }),
    ),
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
