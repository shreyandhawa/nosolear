import type { components } from "../api/schema";

type Job = components["schemas"]["JobOut"];

/** A job's real steps, as the API reports them. */
export function JobSteps({ job }: { job: Job }) {
  return (
    <section aria-label="Job progress" className="mt-4">
      <p>
        {job.status === "done" ? "Done" : job.status === "failed" ? "Failed" : "Working"} ({Math.round(job.progress * 100)}%)
      </p>
      <progress max={1} value={job.progress} />
      <ol className="mt-2 list-decimal pl-6">
        {job.steps.map((s) => (
          <li key={s.name}>
            {s.name}: {s.state}
            {s.message && ` (${s.message})`}
          </li>
        ))}
      </ol>
    </section>
  );
}
