import { useQuery } from "@tanstack/react-query";
import { api } from "../../shared/api/client";
import { must } from "../../shared/api/http";
import { welcomeSeen } from "../../shared/welcomeSeen";

const TARGETS = {
  readiness: "/setup",
  calibration: "/calibration",
  baseline: "/baseline",
  report: "/report",
  daily_plan: "/today",
} as const;

export type HomeTarget = (typeof TARGETS)[keyof typeof TARGETS] | "/welcome";

/** The screen for the step `GET /api/onboarding` names; a first visit sees Welcome first. */
export function useHomeTarget() {
  const onboarding = useQuery({
    queryKey: ["onboarding"],
    queryFn: () => must(api.GET("/api/onboarding"), "GET /api/onboarding"),
  });
  const step = onboarding.data?.step;
  const target: HomeTarget | null =
    step === "readiness" && !welcomeSeen()
      ? "/welcome"
      : step && step in TARGETS
        ? TARGETS[step as keyof typeof TARGETS]
        : null;
  return { onboarding, target };
}
