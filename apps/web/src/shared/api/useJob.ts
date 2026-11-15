import { useQuery } from "@tanstack/react-query";
import { api } from "./client";
import { must } from "./http";

const FINISHED = new Set(["done", "failed"]);

/** Polls a job until it is done or failed. */
export function useJob(jobId: string | null) {
  return useQuery({
    queryKey: ["job", jobId],
    enabled: jobId !== null,
    queryFn: () => must(api.GET("/api/jobs/{job_id}", { params: { path: { job_id: jobId! } } }), "GET job"),
    refetchInterval: (q) => (q.state.data && FINISHED.has(q.state.data.status) ? false : 1000),
  });
}
