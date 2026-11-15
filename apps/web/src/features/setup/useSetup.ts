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
  return {
    readiness,
    envLines: readiness.data ? missingEnvLines(readiness.data.rows) : [],
    blocked: onboarding.data?.step === "readiness",
    probe,
  };
}
