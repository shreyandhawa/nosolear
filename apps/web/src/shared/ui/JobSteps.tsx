import type { components } from "../api/schema";
import { StatusDot } from "./Desk";

type Job = components["schemas"]["JobOut"];

/** A job's real steps, as the API reports them. */
export function JobSteps({ job }: { job: Job }) {
  return (
    <section aria-label="Job progress">
      <p className="num mb-3 text-[2rem] leading-none font-medium">
        {Math.round(job.progress * 100)}%
        <span className="text-[1.0625rem] font-normal text-fg/72">
          {" "}
          {job.status === "done" ? "done" : job.status === "failed" ? "failed" : "analyzing"}
        </span>
      </p>
      <ol className="flex flex-col gap-1.5 text-[0.9375rem]">
        {job.steps.map((s) => (
          <li key={s.name} className="flex items-center gap-2.5">
            <StatusDot ok={s.state === "done"} />
            <span>{s.name}</span>
            <span className="text-fg/72">{s.state}</span>
            {s.message && <span className="text-fg/72">({s.message})</span>}
          </li>
        ))}
      </ol>
    </section>
  );
}
