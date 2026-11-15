import { Link } from "@tanstack/react-router";
import { recordingUrl } from "../../shared/api/http";
import { ClipPlayer } from "../../shared/audio/ClipPlayer";
import { ModelVoice } from "../../shared/audio/ModelVoice";
import { Recorder } from "../../shared/audio/Recorder";
import { useBaseline } from "./useBaseline";

const limits = (max: number | null, startLimit: number | null) =>
  [max && `up to ${max} s`, startLimit && `start within ${startLimit} s`].filter(Boolean).join(", ");

export function BaselinePage() {
  const b = useBaseline();
  const report = b.report;
  return (
    <main className="mx-auto max-w-4xl p-8">
      <h1 className="text-2xl font-semibold">Baseline</h1>
      {b.session.isPending && <p>Loading…</p>}
      {b.session.isError && <p role="alert">{b.session.error.message}</p>}
      {b.session.isSuccess && b.session.data === null && (
        <p className="mt-4">
          The baseline is a set of short readings and answers that measures where you start.{" "}
          <button type="button" className="rounded border px-4 py-2" onClick={() => b.start.mutate()}>
            Start the baseline
          </button>
        </p>
      )}
      {(b.start.error ?? b.complete.error) && <p role="alert">{(b.start.error ?? b.complete.error)?.message}</p>}
      {b.session.data && !b.completed && (
        <>
          <ol className="mt-4 list-decimal pl-6 text-sm">
            {b.items.map((i) => (
              <li key={i.attempt_id}>
                {i.section}: {i.text || i.step} ({limits(i.max_seconds, i.start_limit_seconds) || "no limit"}){" "}
                {i.recorded ? `recorded, ${i.job_status ?? "queued"}` : ""}
              </li>
            ))}
          </ol>
          {b.current && (
            <section className="mt-4" key={b.current.attempt_id}>
              <h2 className="font-semibold">
                Item {b.items.indexOf(b.current) + 1} of {b.items.length}: {b.current.section}
              </h2>
              <p className="mt-2 text-xl">{b.current.text}</p>
              <p>{limits(b.current.max_seconds, b.current.start_limit_seconds)}</p>
              {b.current.scripted && <ModelVoice source="content_item" id={b.current.item_id} />}
              <Recorder attemptId={b.current.attempt_id} maxSeconds={b.current.max_seconds ?? 60} onUploaded={b.recorded} />
            </section>
          )}
          {b.allRecorded && (
            <p className="mt-4">
              All items recorded.{" "}
              <button type="button" className="rounded border px-4 py-2" onClick={() => b.complete.mutate()} disabled={b.complete.isPending}>
                Complete the baseline
              </button>
            </p>
          )}
        </>
      )}
      {report && (
        <section className="mt-4">
          <h2 className="font-semibold">Your report</h2>
          {report.calibration !== "done" && <p>Calibration: {report.calibration}. Flags marked provisional may change.</p>}
          <ul>
            {report.skill_scores.map((s) => (
              <li key={s.skill}>
                {s.skill}: {Math.round(s.score)}
              </li>
            ))}
          </ul>
          <ol className="mt-4 list-decimal pl-6">
            {report.items.map((item) => (
              <li key={item.error_key} className="mt-2">
                {item.description} ({item.skill}, {Math.round(item.p_hat * 100)}% of chances){item.provisional && " provisional"}
                <div className="flex flex-wrap gap-2">
                  {item.clips.map((clip, n) => (
                    <ClipPlayer
                      key={`${clip.attempt_id}-${clip.start_ms}`}
                      src={recordingUrl(clip.attempt_id)}
                      label={clip.word ? `"${clip.word}"` : `Clip ${n + 1}`}
                      startMs={clip.start_ms}
                      endMs={clip.end_ms}
                    />
                  ))}
                </div>
              </li>
            ))}
          </ol>
          {report.notes.map((note) => (
            <p key={note}>{note}</p>
          ))}
          <p className="mt-4">
            <Link to="/today">Start today's session</Link>
          </p>
        </section>
      )}
    </main>
  );
}
