import { useQuery } from "@tanstack/react-query";
import { api } from "../../shared/api/client";
import { must } from "../../shared/api/http";

const TARGETS = {
  readiness: "/setup",
  calibration: "/calibration",
  baseline: "/baseline",
  report: "/report",
  daily_plan: "/today",
} as const;

export type HomeTarget = (typeof TARGETS)[keyof typeof TARGETS];

/** The screen for the step `GET /api/onboarding` names. */
export function useHomeTarget() {
  const onboarding = useQuery({
    queryKey: ["onboarding"],
    queryFn: () => must(api.GET("/api/onboarding"), "GET /api/onboarding"),
  });
  const step = onboarding.data?.step;
  const target: HomeTarget | null = step && step in TARGETS ? TARGETS[step as keyof typeof TARGETS] : null;
  return { onboarding, target };
}
