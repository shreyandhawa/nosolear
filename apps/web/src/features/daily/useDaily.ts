import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useReducer } from "react";
import { api } from "../../shared/api/client";
import { must, orNull } from "../../shared/api/http";
import type { components } from "../../shared/api/schema";
import { useJob } from "../../shared/api/useJob";
import { dailyReducer } from "./dailyReducer";

type Plan = components["schemas"]["PlanOut"];
type Session = components["schemas"]["DailySessionOut"];
type Feedback = components["schemas"]["FeedbackOut"];

export const SPEAK_SECONDS = 60;

export function useDaily() {
  const queryClient = useQueryClient();
  const [state, dispatch] = useReducer(dailyReducer, { phase: "plan" });
  const plan = useQuery({
    queryKey: ["plan-today"],
    queryFn: () => orNull(api.GET("/api/plan/today"), "GET /api/plan/today"),
  });
  const build = useMutation({
    mutationFn: async () => (await must(api.POST("/api/plan/today"), "build today's plan")) as Plan,
    onSuccess: (data) => queryClient.setQueryData(["plan-today"], data),
  });
  const start = useMutation({
    mutationFn: async () => {
      const session = (await must(api.POST("/api/plan/today/session"), "start the session")) as Session;
      const feedback = session.completed
        ? ((await must(
            api.GET("/api/sessions/{session_id}/feedback", { params: { path: { session_id: session.session_id } } }),
            "feedback",
          )) as Feedback)
        : null;
      return { session, feedback };
    },
    onSuccess: ({ session, feedback }) => dispatch({ type: "started", session, feedback }),
  });
  // Opening Today again, after leaving or reloading, rebuilds the stage from the server. Starting
  // is idempotent: it returns the day's open session.
  const { mutate: startSession, isIdle: startIdle } = start;
  useEffect(() => {
    if (plan.data && state.phase === "plan" && startIdle) startSession();
  }, [plan.data, state.phase, startIdle, startSession]);
  const job = useJob(state.phase === "analyze" ? state.jobId : null);
  const feedback = useMutation({
    mutationFn: (sessionId: string) =>
      must(
        api.POST("/api/sessions/{session_id}/feedback", { params: { path: { session_id: sessionId } } }),
        "feedback",
      ) as Promise<Feedback>,
    onSuccess: (data) => dispatch({ type: "feedback", feedback: data }),
  });
  const complete = useMutation({
    mutationFn: (sessionId: string) =>
      must(
        api.POST("/api/sessions/{session_id}/complete", { params: { path: { session_id: sessionId } } }),
        "complete the session",
      ),
    onSuccess: () => {
      dispatch({ type: "completed" });
      void queryClient.invalidateQueries({ queryKey: ["onboarding"] });
      void queryClient.invalidateQueries({ queryKey: ["profile"] });
    },
  });

  const analyzed = state.phase === "analyze" && job.data?.status === "done";
  const sessionId = state.phase === "plan" ? null : state.session.session_id;
  const { mutate: askFeedback, isIdle } = feedback;
  useEffect(() => {
    // One POST when the analysis has finished; the API also refuses a second coach call.
    if (analyzed && sessionId && isIdle) askFeedback(sessionId);
  }, [analyzed, sessionId, isIdle, askFeedback]);

  return {
    state,
    plan,
    build,
    start,
    job: job.data ?? null,
    feedback,
    complete,
    uploaded: (jobId: string) => dispatch({ type: "uploaded", jobId }),
  };
}
