import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../shared/api/client";
import { must, orNull } from "../../shared/api/http";

export function useBaseline() {
  const queryClient = useQueryClient();
  const session = useQuery({
    queryKey: ["baseline"],
    queryFn: () => orNull(api.GET("/api/baseline"), "GET /api/baseline"),
    // While a take is being analyzed, its job status is what "Complete" waits for.
    refetchInterval: (q) =>
      q.state.data?.items.some((i) => i.recorded && i.job_status !== "done" && i.job_status !== "failed") ? 2000 : false,
  });
  const completed = session.data?.completed_at != null;
  const report = useQuery({
    queryKey: ["baseline-report"],
    enabled: completed,
    queryFn: () => orNull(api.GET("/api/baseline/report"), "GET /api/baseline/report"),
  });
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["baseline"] });
    void queryClient.invalidateQueries({ queryKey: ["onboarding"] });
  };
  const start = useMutation({
    mutationFn: () => must(api.POST("/api/baseline"), "start the baseline"),
    onSuccess: (data) => queryClient.setQueryData(["baseline"], data),
  });
  const complete = useMutation({
    mutationFn: () => must(api.POST("/api/baseline/complete"), "complete the baseline"),
    onSuccess: (data) => {
      queryClient.setQueryData(["baseline-report"], data);
      refresh();
    },
  });
  const items = session.data?.items ?? [];
  const index = items.findIndex((i) => !i.recorded);
  return {
    session,
    items,
    current: index === -1 ? null : items[index],
    allRecorded: items.length > 0 && index === -1,
    completed,
    report: report.data ?? null,
    start,
    complete,
    recorded: refresh,
  };
}
