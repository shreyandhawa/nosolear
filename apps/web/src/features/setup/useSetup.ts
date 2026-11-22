import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../shared/api/client";
import { must } from "../../shared/api/http";
import type { components } from "../../shared/api/schema";

type Row = components["schemas"]["ReadinessRowOut"];

/** The `.env` lines still missing, read from the rows whose fix names them. */
export function missingEnvLines(rows: Row[]): string[] {
  const names = rows
    .filter((r) => r.status === "missing" && r.fix?.includes(".env"))
    .flatMap((r) => r.fix?.match(/NOSOLEAR_[A-Z0-9_]+/g) ?? []);
  return [...new Set(names)].map((name) => `${name}=`);
}

const REQUIRED = ["azure_speech", "azure_capabilities"];
const COACH = ["anthropic"];

export function useSetup() {
  const queryClient = useQueryClient();
  const readiness = useQuery({
    queryKey: ["readiness"],
    queryFn: () => must(api.GET("/api/readiness"), "GET /api/readiness"),
  });
  const onboarding = useQuery({
    queryKey: ["onboarding"],
    queryFn: () => must(api.GET("/api/onboarding"), "GET /api/onboarding"),
  });
  const probe = useMutation({
    mutationFn: () => must(api.POST("/api/readiness/probe"), "the check"),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["readiness"] });
      void queryClient.invalidateQueries({ queryKey: ["onboarding"] });
    },
  });
  const rows = readiness.data?.rows ?? [];
  const required = rows.filter((r) => REQUIRED.includes(r.component));
  const coach = rows.filter((r) => COACH.includes(r.component));
  return {
    readiness,
    required,
    coach,
    local: rows.filter((r) => !REQUIRED.includes(r.component) && !COACH.includes(r.component)),
    envLines: missingEnvLines(required),
    coachLines: missingEnvLines(coach),
    blocked: onboarding.data?.step === "readiness",
    probe,
  };
}
