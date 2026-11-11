import type { components } from "../../shared/api/schema";

type Status = components["schemas"]["ProfileEntryOut"]["status"];

const LABELS: Record<Status, string> = {
  unknown: "Not enough data",
  active: "Active",
  improving: "Improving",
  watching: "Watching",
  mastered: "Mastered",
};

export function statusLabel(s: Status): string {
  return LABELS[s];
}
