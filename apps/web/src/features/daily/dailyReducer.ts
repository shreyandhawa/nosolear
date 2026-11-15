import type { components } from "../../shared/api/schema";

type Session = components["schemas"]["DailySessionOut"];
export type Feedback = components["schemas"]["FeedbackOut"];

export type DailyState =
  | { phase: "plan" }
  | { phase: "record"; session: Session }
  | { phase: "analyze"; session: Session; jobId: string }
  | { phase: "feedback"; session: Session; feedback: Feedback }
  | { phase: "done"; session: Session; feedback: Feedback };

export type DailyAction =
  | { type: "started"; session: Session }
  | { type: "uploaded"; jobId: string }
  | { type: "feedback"; feedback: Feedback }
  | { type: "completed" };

export function dailyReducer(state: DailyState, action: DailyAction): DailyState {
  switch (action.type) {
    case "started":
      return state.phase === "plan" ? { phase: "record", session: action.session } : state;
    case "uploaded":
      return state.phase === "record" ? { phase: "analyze", session: state.session, jobId: action.jobId } : state;
    case "feedback":
      return state.phase === "analyze" || state.phase === "feedback"
        ? { phase: "feedback", session: state.session, feedback: action.feedback }
        : state;
    case "completed":
      return state.phase === "feedback" ? { phase: "done", session: state.session, feedback: state.feedback } : state;
  }
}
