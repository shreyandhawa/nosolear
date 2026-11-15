import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../../shared/api/client";
import { must, orNull } from "../../shared/api/http";
import { useJob } from "../../shared/api/useJob";

export function useCalibration() {
  const queryClient = useQueryClient();
  const key = ["calibration"];
  const run = useQuery({
    queryKey: key,
    queryFn: () => orNull(api.GET("/api/calibration"), "GET /api/calibration"),
  });
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: key });
    void queryClient.invalidateQueries({ queryKey: ["onboarding"] });
  };
  const start = useMutation({
    mutationFn: () => must(api.POST("/api/calibration"), "start calibration"),
    onSuccess: (data) => queryClient.setQueryData(key, data),
  });
  const skip = useMutation({
    mutationFn: () => must(api.POST("/api/calibration/skip"), "skip calibration"),
    onSuccess: (data) => {
      queryClient.setQueryData(key, data);
      refresh();
    },
  });
  const [jobId, setJobId] = useState<string | null>(null);
  const finish = useMutation({
    mutationFn: () => must(api.POST("/api/calibration/finish"), "finish calibration"),
    onSuccess: (accepted) => setJobId(accepted.job_id),
  });
  const job = useJob(jobId);
  const jobDone = job.data?.status === "done" || job.data?.status === "failed";
  useEffect(() => {
    if (jobDone) refresh();
  }, [jobDone]);

  const items = run.data?.items ?? [];
  const index = items.findIndex((i) => !i.recorded);
  return {
    run,
    items,
    current: index === -1 ? null : items[index],
    position: index === -1 ? items.length : index + 1,
    allRecorded: items.length > 0 && index === -1,
    start,
    skip,
    finish,
    job: job.data ?? null,
    recorded: refresh,
  };
}
