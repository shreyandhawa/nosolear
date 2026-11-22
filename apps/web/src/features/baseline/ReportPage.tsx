import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { recordingUrl } from "../../shared/api/http";
import { ClipPlayer } from "../../shared/audio/ClipPlayer";
import { MicStage } from "../../shared/audio/MicStage";
import { PhoneticPair } from "../../shared/ui/PhoneticPair";
import { Desk, Label, releaseFocus, TitleBlock } from "../../shared/ui/Desk";
import { ctaLink } from "../../shared/ui/styles";
import { useBaseline } from "./useBaseline";

const SKILLS: Record<string, string> = { sounds: "Sounds", on_the_spot: "On the spot", articulate: "Articulate" };

export function ReportPage() {
  const b = useBaseline();
  const report = b.report;
  const [picked, setPicked] = useState(0);

  if (!report) {
    const waiting = b.session.isPending || b.completed;
    return (
      <Desk
        stateKey="none"
        title={<TitleBlock step="Report" sub={waiting ? "Loading…" : "Your report appears once the baseline is complete"} />}
        stage={<MicStage state="idle" hint="No report yet" />}
        cta={
          !waiting && (
            <Link to="/baseline" className={ctaLink}>
              Go to the baseline
            </Link>
          )
        }
      />
    );
  }

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
                  className="press -mx-2 flex w-[calc(100%+1rem)] items-baseline gap-2 px-2 py-1.5 text-left hover:bg-fg/6 aria-pressed:bg-fg aria-pressed:text-bg"
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
