import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { recordingUrl } from "../../shared/api/http";
import { ClipPlayer } from "../../shared/audio/ClipPlayer";
import { MicStage, type MicState } from "../../shared/audio/MicStage";
import { ModelVoice } from "../../shared/audio/ModelVoice";
import { useTake } from "../../shared/audio/useTake";
import { PhoneticPair } from "../../shared/ui/PhoneticPair";
import { Cta, Desk, Label, releaseFocus, StatusDot, TitleBlock } from "../../shared/ui/Desk";
import { ctaLink } from "../../shared/ui/styles";
import { useBaseline } from "./useBaseline";

const SKILLS: Record<string, string> = { sounds: "Sounds", on_the_spot: "On the spot", articulate: "Articulate" };
const PURPOSE = "The baseline is a set of short readings and answers that measures where you start.";

const limits = (max: number | null, startLimit: number | null) =>
  [max && `Up to ${max} s`, startLimit && `start within ${startLimit} s`].filter(Boolean).join(", ");

export function BaselinePage() {
  const b = useBaseline();
  const report = b.report;
  const [picked, setPicked] = useState(0);
  const item = !b.completed ? b.current : null;
  const take = useTake(item?.attempt_id ?? null, item?.max_seconds ?? 60, b.recorded);
  const error = b.start.error ?? b.complete.error;

  if (report) {
    const ranked = report.items;
    const top = ranked[Math.min(picked, ranked.length - 1)];
    return (
      <Desk
        stateKey={`report-${picked}`}
        title={
          <TitleBlock step={`Report, error ${picked + 1} of ${ranked.length}`} sub={top?.description}>
            {top && <PhoneticPair errorKey={top.error_key} fallback={top.description} />}
          </TitleBlock>
        }
        media={
          top && (
            <div className="flex flex-col gap-3">
              <Label>Your clips</Label>
              <div className="flex flex-wrap gap-2">
                {top.clips.map((clip, n) => (
                  <ClipPlayer
                    key={`${clip.attempt_id}-${clip.start_ms}`}
                    src={recordingUrl(clip.attempt_id)}
                    label={clip.word ? `“${clip.word}”` : `Clip ${n + 1}`}
                    startMs={clip.start_ms}
                    endMs={clip.end_ms}
                  />
                ))}
              </div>
            </div>
          )
        }
        text={
          top && (
            <>
              <p className="num">
                {Math.round(top.p_hat * 100)}% of chances <span className="text-fg/72">({Math.round(top.ci_low * 100)}–{Math.round(top.ci_high * 100)}%)</span>
              </p>
              <p className="mt-1 text-fg/72">
                {SKILLS[top.skill]}, {top.status}
                {top.provisional && ", provisional"}
              </p>
              {report.calibration !== "done" && (
                <p className="mt-3 text-[0.9375rem]">Calibration: {report.calibration}. Provisional flags may change.</p>
              )}
              {report.notes.map((note) => (
                <p key={note} className="mt-3 text-[0.9375rem]">
                  {note}
                </p>
              ))}
            </>
          )
        }
        stage={<MicStage state="idle" hint="Your baseline is recorded" />}
        card={
          <>
            <Label>Score per skill</Label>
            <ul className="flex flex-col gap-2">
              {report.skill_scores.map((s) => (
                <li key={s.skill} className="flex items-baseline justify-between">
                  <span>{SKILLS[s.skill] ?? s.skill}</span>
                  <span className="num font-display text-[1.75rem] leading-none">{Math.round(s.score)}</span>
                </li>
              ))}
            </ul>
          </>
        }
        note={
          <>
            <Label>Ranked errors</Label>
            <ol className="flex flex-col gap-1">
              {ranked.map((r, i) => (
                <li key={r.error_key}>
                  <button
                    type="button"
                    aria-pressed={i === picked}
                    onClick={(e) => {
                      setPicked(i);
                      releaseFocus(e);
                    }}
                    className="press -mx-2 flex w-[calc(100%+1rem)] items-baseline gap-2 rounded px-2 py-1.5 text-left hover:bg-fg/6 aria-pressed:bg-fg aria-pressed:text-bg"
                  >
                    <span className="num w-5 shrink-0 opacity-70">{i + 1}</span>
                    <span>{r.description}</span>
                  </button>
                </li>
              ))}
            </ol>
          </>
        }
        cta={
          <Link to="/today" className={ctaLink}>
            Start today's session
          </Link>
        }
      />
    );
  }

  const session = b.session.data;
  const index = item ? b.items.indexOf(item) : -1;
  const state: MicState =
    take.phase === "recording"
      ? "recording"
      : take.phase === "error"
        ? "error"
        : take.phase === "uploading"
          ? "analyzing"
          : take.phase === "ready"
            ? "ready"
            : b.allRecorded
              ? "done"
              : "idle";
  const long = (item?.text.length ?? 0) > 28;
  return (
    <Desk
      stateKey={!session ? "none" : item ? `item-${item.attempt_id}` : "recorded"}
      title={
        item ? (
          <TitleBlock step={`Baseline, item ${index + 1} of ${b.items.length}`}>
            <span className={long ? "block text-[clamp(2rem,2.8vw,2.75rem)] leading-tight" : undefined}>{item.text}</span>
          </TitleBlock>
        ) : (
          <TitleBlock
            step="Baseline"
            sub={b.session.isPending ? "Loading…" : session ? `All ${b.items.length} items recorded` : undefined}
          />
        )
      }
      media={item?.scripted && <ModelVoice source="content_item" id={item.item_id} />}
      text={
        item && (
          <>
            <p className="font-display text-[1.375rem]">{item.section}</p>
            <p className="text-fg/72">{limits(item.max_seconds, item.start_limit_seconds) || "No time limit"}</p>
          </>
        )
      }
      stage={
        <MicStage
          state={state}
          elapsed={take.elapsed}
          maxSeconds={item?.max_seconds ?? 60}
          getLevel={take.getLevel}
          onPress={take.canToggle ? take.toggle : undefined}
          hint={take.phase === "recording" ? "Space to stop" : take.phase === "ready" ? "Space to start" : "The microphone opens for each item"}
        />
      }
      card={
        <>
          <Label>This step</Label>
          <p>{PURPOSE}</p>
          {session && (
            <ol className="mt-4 flex flex-col gap-1 text-[0.875rem]">
              {b.items.map((i) => (
                <li key={i.attempt_id} className="flex items-center gap-2">
                  <StatusDot ok={i.recorded} />
                  <span className="truncate">{i.section}</span>
                  <span className="ml-auto shrink-0 text-fg/72">{i.recorded ? (i.job_status ?? "queued") : ""}</span>
                </li>
              ))}
            </ol>
          )}
        </>
      }
      note={
        error || take.message ? (
          <p role="alert">
            {error?.message ?? take.message}
            {take.retry && (
              <button type="button" className="ml-1 underline underline-offset-4" onClick={take.retry}>
                Retry upload
              </button>
            )}
          </p>
        ) : (
          item && <p>{item.scripted ? "Read it as written." : "Answer in your own words."}</p>
        )
      }
      cta={
        !session ? (
          b.session.isSuccess && (
            <Cta onClick={() => b.start.mutate()} disabled={b.start.isPending}>
              Start the baseline
            </Cta>
          )
        ) : item ? (
          <Cta onClick={take.toggle} disabled={!take.canToggle} aria-pressed={take.phase === "recording"}>
            {take.phase === "recording" ? "Stop" : take.phase === "uploading" ? "Saving take" : "Record"}
          </Cta>
        ) : (
          <Cta onClick={() => b.complete.mutate()} disabled={b.complete.isPending}>
            Complete the baseline
          </Cta>
        )
      }
    />
  );
}
