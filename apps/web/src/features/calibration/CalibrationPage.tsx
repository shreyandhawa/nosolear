import { Link } from "@tanstack/react-router";
import { ModelVoice } from "../../shared/audio/ModelVoice";
import { Recorder } from "../../shared/audio/Recorder";
import { JobSteps } from "../../shared/ui/JobSteps";
import { useCalibration } from "./useCalibration";

const pct = (x: number | null) => (x === null ? "–" : `${Math.round(x * 100)}%`);

export function CalibrationPage() {
  const c = useCalibration();
  const run = c.run.data;
  return (
    <main className="mx-auto max-w-4xl p-8">
      <h1 className="text-2xl font-semibold">Calibration</h1>
      {c.run.isPending && <p>Loading…</p>}
      {c.run.isError && <p role="alert">{c.run.error.message}</p>}
      {c.run.isSuccess && (run === null || run?.status === "skipped") && (
        <section className="mt-4">
          <p>Calibration tunes the detectors to your voice: one short word per screen, said as asked.</p>
          {run?.status === "skipped" && <p>You skipped calibration. Scores stay provisional until you calibrate.</p>}
          <button type="button" className="rounded border px-4 py-2" onClick={() => c.start.mutate()}>
            Start calibration
          </button>{" "}
          {run === null && (
            <button type="button" className="rounded border px-4 py-2" onClick={() => c.skip.mutate()}>
              Skip
            </button>
          )}
          {run?.status === "skipped" && <Link to="/baseline">Go to the baseline</Link>}
        </section>
      )}
      {(c.start.error ?? c.skip.error ?? c.finish.error) && (
        <p role="alert">{(c.start.error ?? c.skip.error ?? c.finish.error)?.message}</p>
      )}
      {run?.status === "running" && c.current && (
        <section className="mt-4" key={c.current.attempt_id}>
          <p>
            Take {c.position} of {c.items.length}
          </p>
          <h2 className="mt-2 text-3xl">{c.current.word}</h2>
          <p className="mt-2">{c.current.instruction}</p>
          <p className="mt-2">
            <ModelVoice source="content_item" id={c.current.item_id} />
          </p>
          <Recorder attemptId={c.current.attempt_id} maxSeconds={10} onUploaded={c.recorded} />
        </section>
      )}
      {run?.status === "running" && c.allRecorded && !c.job && (
        <p className="mt-4">
          All {c.items.length} takes recorded.{" "}
          <button type="button" className="rounded border px-4 py-2" onClick={() => c.finish.mutate()} disabled={c.finish.isPending}>
            Finish calibration
          </button>
        </p>
      )}
      {c.job && <JobSteps job={c.job} />}
      {run?.status === "done" && (
        <section className="mt-4">
          <h2 className="font-semibold">Result</h2>
          <table className="w-full text-left text-sm">
            <thead>
              <tr>
                <th>Detector</th>
                <th>Error</th>
                <th>Enabled</th>
                <th>Hit rate</th>
                <th>False alarms</th>
                <th>Warning</th>
              </tr>
            </thead>
            <tbody>
              {run.results.map((r) => (
                <tr key={`${r.detector}-${r.error_key}`}>
                  <td>{r.detector}</td>
                  <td>{r.error_key}</td>
                  <td>{r.enabled ? "yes" : "no"}</td>
                  <td>{pct(r.hit_rate)}</td>
                  <td>{pct(r.false_alarm_rate)}</td>
                  <td>{r.warning}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-4">
            <Link to="/baseline">Go to the baseline</Link>
          </p>
        </section>
      )}
    </main>
  );
}
