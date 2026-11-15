import { useQuery } from "@tanstack/react-query";
import { api } from "../shared/api/client";
import { must } from "../shared/api/http";

/** What the navigation shows: the onboarding step, readiness and usage. Read-only GETs. */
export function useNav() {
  const onboarding = useQuery({
    queryKey: ["onboarding"],
    queryFn: () => must(api.GET("/api/onboarding"), "GET /api/onboarding"),
  });
  const readiness = useQuery({
    queryKey: ["readiness"],
    queryFn: () => must(api.GET("/api/readiness"), "GET /api/readiness"),
  });
  const step = onboarding.data?.step;
  return {
    step,
    firstRun: step !== undefined && step !== "daily_plan",
    ready: readiness.data?.ready ?? false,
    usage: readiness.data?.rows.find((r) => r.component === "usage")?.reason ?? null,
  };
}
