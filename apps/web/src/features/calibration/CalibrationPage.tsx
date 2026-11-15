import { Link } from "@tanstack/react-router";
import { MicStage, type MicState } from "../../shared/audio/MicStage";
import { ModelVoice } from "../../shared/audio/ModelVoice";
import { useTake } from "../../shared/audio/useTake";
import { Action, Cta, Desk, Label, TitleBlock } from "../../shared/ui/Desk";
import { JobSteps } from "../../shared/ui/JobSteps";
import { ctaLink } from "../../shared/ui/styles";
import { useCalibration } from "./useCalibration";

const TAKE_SECONDS = 10;
const pct = (x: number | null) => (x === null ? "–" : `${Math.round(x * 100)}%`);
const PURPOSE = "Calibration tunes the detectors to your voice: one short word per screen, said as asked.";

export function CalibrationPage() {
  const c = useCalibration();
  const run = c.run.data;
  const running = run?.status === "running";
  const take = useTake(running && c.current ? c.current.attempt_id : null, TAKE_SECONDS, c.recorded);
  const error = c.start.error ?? c.skip.error ?? c.finish.error;
  const finishing = c.job !== null && run?.status !== "done";
  const enabled = run?.results.filter((r) => r.enabled).length ?? 0;

  const state: MicState = finishing
    ? "analyzing"
    : take.phase === "recording"
      ? "recording"
      : take.phase === "error"
        ? "error"
        : take.phase === "uploading"
          ? "analyzing"
          : take.phase === "ready"
            ? "ready"
            : run?.status === "done"
              ? "done"
              : "idle";

  const stateKey = !run ? "none" : finishing ? "finishing" : run.status === "running" ? `take-${c.current?.attempt_id ?? "all"}` : run.status;

  const title = !run ? (
    <TitleBlock step="Calibration" sub={c.run.isPending ? "Loading…" : undefined} />
  ) : run.status === "running" && c.current ? (
    <TitleBlock step={`Calibration, take ${c.position} of ${c.items.length}`}>{c.current.word}</TitleBlock>
  ) : run.status === "done" ? (
    <TitleBlock step="Calibration done" sub="detectors on for your voice">
      {enabled} of {run.results.length}
    </TitleBlock>
  ) : run.status === "skipped" ? (
    <TitleBlock step="Calibration skipped" />
  ) : (
    <TitleBlock step="Calibration" sub={`All ${c.items.length} takes recorded`} />
  );

  return (
    <Desk
      stateKey={stateKey}
      title={title}
      media={
        finishing && c.job ? (
          <JobSteps job={c.job} />
        ) : (
          running && c.current && <ModelVoice source="content_item" id={c.current.item_id} />
        )
      }
      text={
        running && c.current ? (
          <p className="font-display text-[1.375rem] leading-snug">{c.current.instruction}</p>
        ) : (
          run?.status === "done" && (
            <table className="w-full text-left text-[0.875rem]">
              <thead className="text-ink/70">
                <tr>
                  <th className="pb-1 font-medium">Error</th>
                  <th className="pb-1 font-medium">On</th>
                  <th className="pb-1 font-medium">Hits</th>
                  <th className="pb-1 font-medium">False alarms</th>
                </tr>
              </thead>
              <tbody className="num">
                {run.results.map((r) => (
                  <tr key={`${r.detector}-${r.error_key}`} className="border-t border-ink/10">
                    <td className="py-1">{r.error_key}</td>
                    <td>{r.enabled ? "yes" : "no"}</td>
                    <td>{pct(r.hit_rate)}</td>
                    <td>{pct(r.false_alarm_rate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        )
      }
      stage={
        <MicStage
          state={state}
          progress={c.job?.progress ?? 0}
          elapsed={take.elapsed}
          maxSeconds={TAKE_SECONDS}
          getLevel={take.getLevel}
          onPress={take.canToggle ? take.toggle : undefined}
          hint={take.phase === "recording" ? "Space to stop" : take.phase === "ready" ? "Space to start" : finishing ? "Scoring your takes" : "The microphone opens for each take"}
        />
      }
      card={
        <>
          <Label>This step</Label>
          <p>{PURPOSE}</p>
          {running && (
            <p className="num mt-3 text-ink/70">
              {c.items.length - c.position + (c.current ? 1 : 0)} of {c.items.length} takes left
            </p>
          )}
          {!run && c.run.isSuccess && (
            <Action className="mt-4" onClick={() => c.skip.mutate()} disabled={c.skip.isPending}>
              Skip calibration
            </Action>
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
        ) : running && c.current?.deliberate ? (
          <p>This take is a deliberate error: it teaches the detector what to listen for.</p>
        ) : (
          <p>Scores stay provisional if you skip.</p>
        )
      }
      cta={
        !run ? (
          c.run.isSuccess && (
            <Cta onClick={() => c.start.mutate()} disabled={c.start.isPending}>
              Start calibration
            </Cta>
          )
        ) : run.status === "running" && c.current ? (
          <Cta onClick={take.toggle} disabled={!take.canToggle} aria-pressed={take.phase === "recording"}>
            {take.phase === "recording" ? "Stop" : take.phase === "uploading" ? "Saving take" : "Record"}
          </Cta>
        ) : run.status === "running" ? (
          <Cta onClick={() => c.finish.mutate()} disabled={c.finish.isPending || finishing}>
            {finishing ? "Scoring" : "Finish calibration"}
          </Cta>
        ) : (
          <Link to="/baseline" className={ctaLink}>
            Go to the baseline
          </Link>
        )
      }
    />
  );
}
