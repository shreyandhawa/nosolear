import { useState } from "react";
import { recordingUrl } from "../../shared/api/http";
import type { components } from "../../shared/api/schema";
import { ClipPlayer } from "../../shared/audio/ClipPlayer";
import { MicStage, type MicState } from "../../shared/audio/MicStage";
import { ModelVoice } from "../../shared/audio/ModelVoice";
import { Transport } from "../../shared/audio/Transport";
import { useTake } from "../../shared/audio/useTake";
import { statusLabel } from "../../shared/statusLabel";
import { PhoneticPair as Pair } from "../../shared/ui/PhoneticPair";
import { Cta, Desk, Label, releaseFocus, StatusDot, TitleBlock } from "../../shared/ui/Desk";
import { JobSteps } from "../../shared/ui/JobSteps";
import { SPEAK_SECONDS, useDaily } from "./useDaily";

type Plan = components["schemas"]["PlanOut"];
type SkillFeedback = components["schemas"]["SkillFeedbackOut"];

const SKILLS: Record<string, string> = { sounds: "Sounds", on_the_spot: "On the spot", articulate: "Articulate" };
const STATES: Record<string, string> = { fix: "One fix", clean: "Clean", not_scored: "Not scored today" };
const REASONS: Record<string, string> = {
  cap_exceeded: "today's coach cap is used up",
  provider_unavailable: "the coach could not be reached",
  capability_missing: "the coach is not set up",
  invalid_output: "the coach's answer could not be used",
};
const STEPS: Record<string, string> = {
  speak: "Speak",
  analyze: "Analyze",
  feedback: "Feedback",
  drill: "Drill",
  log: "Log",
};

const dateLabel = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });


function PlanSlots(plan: Plan) {
  const sounds = plan.foci.find((f) => f.skill === "sounds");
  return {
    title: (
      <TitleBlock step={dateLabel(plan.for_date)} sub={sounds?.description}>
        {sounds && <Pair errorKey={sounds.error_key} fallback={sounds.description} />}
      </TitleBlock>
    ),
    card: (
      <>
        <Label>Today's focuses</Label>
        <ul className="flex flex-col gap-4">
          {plan.foci.map((f) => (
            <li key={f.skill}>
              <p className="text-[0.8125rem] font-medium text-fg/72">{SKILLS[f.skill]}</p>
              <p className="leading-snug">{f.description}</p>
              <p className="flex items-center gap-1.5 text-[0.8125rem] text-fg/72">
                <StatusDot ok={f.status === "mastered" || f.status === "improving"} />
                {statusLabel(f.status)}
                {f.provisional && ", provisional"}
              </p>
            </li>
          ))}
        </ul>
      </>
    ),
    note: (
      <>
        <Label>The plan</Label>
        <ol className="flex flex-col gap-1.5">
          {plan.steps.map((s, i) => (
            <li key={i} className="flex justify-between gap-3">
              <span>
                {STEPS[s.kind] ?? s.kind}
                {s.skill && <span className="text-fg/72"> · {SKILLS[s.skill]}</span>}
              </span>
              <span className="num shrink-0 whitespace-nowrap text-fg/72">{Math.max(1, Math.round(s.duration_s / 60))} min</span>
            </li>
          ))}
        </ol>
      </>
    ),
  };
}

function FeedbackSlots(skill: SkillFeedback) {
  const item = skill.item;
  return {
    title: (
      <TitleBlock step={`${SKILLS[skill.skill]}, ${STATES[skill.state].toLowerCase()}`}>
        {item ? (item.word ?? <Pair errorKey={item.error_key} fallback={item.error_key} />) : STATES[skill.state]}
      </TitleBlock>
    ),
    media: item && (
      <div className="flex flex-col gap-3">
        <Label>You and the model</Label>
        {item.attempt_id && (
          <div className="flex items-center gap-2">
            <span className="mr-1 text-[0.8125rem] font-medium text-fg/72">You</span>
            <ClipPlayer src={recordingUrl(item.attempt_id)} label="Your clip" startMs={item.start_ms} endMs={item.end_ms} />
          </div>
        )}
        {item.model_text && <ModelVoice source="feedback_item" id={item.id} />}
      </div>
    ),
    text: item && (
      <dl className="grid grid-cols-2 gap-4">
        <div>
          <dt className="text-[0.8125rem] font-medium text-fg/72">Your word</dt>
          <dd className="font-display text-[1.375rem]">{item.word ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-[0.8125rem] font-medium text-fg/72">Say it like this</dt>
          <dd className="font-display text-[1.375rem]">{item.model_text ?? "—"}</dd>
        </div>
      </dl>
    ),
    note: item ? (
      <>
        <p>{item.message}</p>
        {item.source === "template" && (
          <p className="mt-3 text-[0.9375rem] text-fg/72">
            Template fallback{item.fallback_reason ? `: ${REASONS[item.fallback_reason] ?? item.fallback_reason}` : ""}.
          </p>
        )}
      </>
    ) : (
      <p>{skill.state === "clean" ? "Nothing to fix in this skill today." : "This skill was not scored today."}</p>
    ),
  };
}

export function DailyPage() {
  const d = useDaily();
  const plan = d.plan.data;
  const s = d.state;
  const attempt = s.phase === "record" ? s.session.attempts[0] : null;
  const take = useTake(attempt?.id ?? null, SPEAK_SECONDS, (a) => d.uploaded(a.job_id));
  const [picked, setPicked] = useState(0);
  const error = d.build.error ?? d.start.error ?? d.feedback.error ?? d.complete.error;

  if (s.phase === "feedback" || s.phase === "done") {
    const skills = s.feedback.skills;
    const skill = skills[Math.min(picked, skills.length - 1)];
    const last = picked >= skills.length - 1;
    const slots = FeedbackSlots(skill);
    return (
      <Desk
        stateKey={`feedback-${skill.skill}-${s.phase}`}
        {...slots}
        stage={<MicStage state={s.phase === "done" ? "done" : "idle"} hint="Today's take is in" />}
        card={
          <>
            <Label>Feedback</Label>
            <div role="group" aria-label="Skills" className="flex flex-col gap-1">
              {skills.map((k, i) => (
                <button
                  key={k.skill}
                  type="button"
                  aria-pressed={i === picked}
                  onClick={(e) => {
                    setPicked(i);
                    releaseFocus(e);
                  }}
                  className="press -mx-2 flex items-center justify-between gap-2 rounded px-2 py-2 text-left hover:bg-fg/6 aria-pressed:bg-fg aria-pressed:text-bg"
                >
                  <span className="font-medium">{SKILLS[k.skill]}</span>
                  <span className="text-[0.8125rem] opacity-75">{STATES[k.state]}</span>
                </button>
              ))}
            </div>
            {s.feedback.degraded && (
              <p className="mt-3 text-[0.8125rem] text-fg/72">Some cards use the template fallback today.</p>
            )}
          </>
        }
        cta={
          s.phase === "done" ? (
            <p className="w-full py-4 text-fg/72">Session complete. See you tomorrow.</p>
          ) : last ? (
            <Cta onClick={() => d.complete.mutate(s.session.session_id)} disabled={d.complete.isPending}>
              Finish session
            </Cta>
          ) : (
            <Cta onClick={() => setPicked(picked + 1)}>Next skill</Cta>
          )
        }
      />
    );
  }

  const planSlots = plan ? PlanSlots(plan) : null;
  const analyzing = s.phase === "analyze";
  const micState: MicState = analyzing
    ? "analyzing"
    : take.phase === "error"
      ? "error"
      : take.phase === "recording"
        ? "recording"
        : take.phase === "uploading" || take.phase === "uploaded"
          ? "analyzing"
          : attempt || plan
            ? "ready"
            : "idle";
  const begin = () => (attempt ? take.toggle() : d.start.mutate());
  const canAct = plan && s.phase !== "analyze" && (attempt ? take.canToggle : !d.start.isPending);

  return (
    <Desk
      stateKey={s.phase}
      title={planSlots?.title ?? <TitleBlock step="Today" sub={d.plan.isPending ? "Loading…" : undefined} />}
      media={
        analyzing ? (
          d.job ? (
            <JobSteps job={d.job} />
          ) : (
            <p>Analyzing…</p>
          )
        ) : (
          plan && <Transport take={take} />
        )
      }
      text={
        plan && (
          <>
            <Label>Today's prompt</Label>
            <p className="font-display text-[1.5rem] leading-snug">{attempt?.prompt_text ?? plan.prompt?.text}</p>
          </>
        )
      }
      stage={
        <MicStage
          state={micState}
          progress={d.job?.progress ?? 0}
          elapsed={take.elapsed}
          maxSeconds={SPEAK_SECONDS}
          getLevel={take.getLevel}
          onPress={canAct ? begin : undefined}
          hint={
            take.phase === "recording"
              ? "Space to stop"
              : analyzing || take.phase === "uploading"
                ? "Analyzing your take"
                : attempt
                  ? "Space to start"
                  : plan
                    ? "Press to start speaking"
                    : "Build today's plan first"
          }
        />
      }
      card={planSlots?.card}
      note={
        error || take.message || (analyzing && d.job?.status === "failed") ? (
          <p role="alert">
            {error?.message ?? take.message ?? "The analysis failed."}
            {take.retry && (
              <button type="button" className="ml-1 underline underline-offset-4" onClick={take.retry}>
                Retry upload
              </button>
            )}
          </p>
        ) : (
          planSlots?.note
        )
      }
      cta={
        d.plan.isSuccess && plan === null ? (
          <Cta onClick={() => d.build.mutate()} disabled={d.build.isPending}>
            Build today's plan
          </Cta>
        ) : analyzing || take.phase === "uploading" || take.phase === "uploaded" ? (
          <Cta disabled>{d.feedback.isPending ? "Writing feedback" : "Analyzing"}</Cta>
        ) : (
          plan && (
            <Cta onClick={begin} disabled={!canAct} aria-pressed={take.phase === "recording"}>
              {take.phase === "recording" ? "Stop" : "Start speaking"}
            </Cta>
          )
        )
      }
    />
  );
}
