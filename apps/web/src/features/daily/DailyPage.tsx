import { recordingUrl } from "../../shared/api/http";
import type { components } from "../../shared/api/schema";
import { ClipPlayer } from "../../shared/audio/ClipPlayer";
import { ModelVoice } from "../../shared/audio/ModelVoice";
import { Recorder } from "../../shared/audio/Recorder";
import { JobSteps } from "../../shared/ui/JobSteps";
import { SPEAK_SECONDS, useDaily } from "./useDaily";

type SkillFeedback = components["schemas"]["SkillFeedbackOut"];

const SKILLS: Record<string, string> = { sounds: "Sounds", on_the_spot: "On the spot", articulate: "Articulate" };
const REASONS: Record<string, string> = {
  cap_exceeded: "today's coach cap is used up",
  provider_unavailable: "the coach could not be reached",
  capability_missing: "the coach is not set up",
  invalid_output: "the coach's answer could not be used",
};

function FeedbackCard({ skill }: { skill: SkillFeedback }) {
  const item = skill.item;
  return (
    <article className="mt-4 rounded border p-4">
      <h3 className="font-semibold">{SKILLS[skill.skill] ?? skill.skill}</h3>
      {skill.state === "not_scored" && <p>Not scored today.</p>}
      {skill.state === "clean" && <p>Clean: nothing to fix today.</p>}
      {skill.state === "fix" && item && (
        <>
          <p>{item.message}</p>
          {item.word && <p>Word: {item.word}</p>}
          {item.model_text && <p>Say it like this: {item.model_text}</p>}
          <p className="mt-2 flex flex-wrap gap-2">
            {item.attempt_id && (
              <ClipPlayer src={recordingUrl(item.attempt_id)} label="Your clip" startMs={item.start_ms} endMs={item.end_ms} />
            )}
            {item.model_text && <ModelVoice source="feedback_item" id={item.id} />}
          </p>
          {item.source === "template" && (
            <p className="text-sm">
              Template fallback{item.fallback_reason ? `: ${REASONS[item.fallback_reason] ?? item.fallback_reason}` : ""}.
            </p>
          )}
        </>
      )}
    </article>
  );
}

export function DailyPage() {
  const d = useDaily();
  const plan = d.plan.data;
  const s = d.state;
  const attempt = s.phase === "plan" ? null : s.session.attempts[0];
  const error = d.build.error ?? d.start.error ?? d.feedback.error ?? d.complete.error;
  return (
    <main className="mx-auto max-w-4xl p-8">
      <h1 className="text-2xl font-semibold">Today</h1>
      {d.plan.isPending && <p>Loading…</p>}
      {d.plan.isError && <p role="alert">{d.plan.error.message}</p>}
      {error && <p role="alert">{error.message}</p>}
      {d.plan.isSuccess && plan === null && (
        <button type="button" className="mt-4 rounded border px-4 py-2" onClick={() => d.build.mutate()}>
          Build today's plan
        </button>
      )}
      {plan && s.phase === "plan" && (
        <section className="mt-4">
          <h2 className="font-semibold">Plan for {plan.for_date}</h2>
          <ul>
            {plan.foci.map((f) => (
              <li key={f.skill}>
                {SKILLS[f.skill]}: {f.description}
                {f.provisional && " (provisional)"}
              </li>
            ))}
          </ul>
          <button type="button" className="mt-4 rounded border px-4 py-2" onClick={() => d.start.mutate()} disabled={d.start.isPending}>
            Start
          </button>
        </section>
      )}
      {s.phase === "record" && attempt && (
        <section className="mt-4">
          <h2 className="font-semibold">Prompt</h2>
          <p className="text-xl">{attempt.prompt_text ?? plan?.prompt?.text}</p>
          <p>Speak for up to {SPEAK_SECONDS} seconds.</p>
          <Recorder attemptId={attempt.id} maxSeconds={SPEAK_SECONDS} onUploaded={(a) => d.uploaded(a.job_id)} />
        </section>
      )}
      {s.phase === "analyze" && (d.job ? <JobSteps job={d.job} /> : <p>Analyzing…</p>)}
      {s.phase === "analyze" && d.job?.status === "failed" && <p role="alert">The analysis failed.</p>}
      {d.feedback.isPending && <p>Writing feedback…</p>}
      {(s.phase === "feedback" || s.phase === "done") && (
        <section className="mt-4">
          <h2 className="font-semibold">Feedback</h2>
          {s.feedback.degraded && <p>Some cards use the template fallback today.</p>}
          {s.feedback.skills.map((skill) => (
            <FeedbackCard key={skill.skill} skill={skill} />
          ))}
          {s.phase === "feedback" ? (
            <button
              type="button"
              className="mt-4 rounded border px-4 py-2"
              onClick={() => d.complete.mutate(s.session.session_id)}
              disabled={d.complete.isPending}
            >
              Complete the session
            </button>
          ) : (
            <p className="mt-4">Session complete. See you tomorrow.</p>
          )}
        </section>
      )}
    </main>
  );
}
