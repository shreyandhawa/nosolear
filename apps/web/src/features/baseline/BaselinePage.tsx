import { Navigate } from "@tanstack/react-router";
import { MicStage, type MicState } from "../../shared/audio/MicStage";
import { ModelVoice } from "../../shared/audio/ModelVoice";
import { useTake } from "../../shared/audio/useTake";
import { Cta, Desk, Label, StatusDot, TitleBlock } from "../../shared/ui/Desk";
import { useBaseline } from "./useBaseline";

const PURPOSE = "The baseline is a set of short readings and answers that measures where you start.";

const limits = (max: number | null, startLimit: number | null) =>
  [max && `Up to ${max} s`, startLimit && `start within ${startLimit} s`].filter(Boolean).join(", ");

export function BaselinePage() {
  const b = useBaseline();
  const item = !b.completed ? b.current : null;
  const take = useTake(item?.attempt_id ?? null, item?.max_seconds ?? 60, b.recorded);
  const error = b.start.error ?? b.complete.error;

  // The report lives on its own page once the baseline is complete.
  if (b.completed) return <Navigate to="/report" />;

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
