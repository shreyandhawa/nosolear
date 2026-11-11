import type { components } from "../../shared/api/schema";
import { formatRate } from "./formatRate";
import { statusLabel } from "./statusLabel";
import { useProfile } from "./useProfile";

const SKILL_LABELS: Record<components["schemas"]["ProfileEntryOut"]["skill"], string> = {
  sounds: "Sounds",
  on_the_spot: "On the spot",
  articulate: "Articulate",
};

export function ProfilePage() {
  const { data, isPending, isError } = useProfile();

  return (
    <main className="mx-auto max-w-4xl p-8">
      <h1 className="text-2xl font-semibold">Profile</h1>
      {isPending && <p className="mt-4 text-slate-600">Loading…</p>}
      {isError && (
        <p role="alert" className="mt-4 text-red-700">
          Couldn't load your profile. Is the API running?
        </p>
      )}
      {data && data.entries.length === 0 && (
        <p className="mt-4 text-slate-600">
          No practice data yet. Your baseline will fill this in.
        </p>
      )}
      {data && data.entries.length > 0 && (
        <table className="mt-4 w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-300">
              <th className="py-2">Problem</th>
              <th>Skill</th>
              <th>Status</th>
              <th>Miss rate</th>
              <th>Evidence</th>
            </tr>
          </thead>
          <tbody>
            {data.entries.map((e) => (
              <tr key={e.error_key} className="border-b border-slate-200">
                <td className="py-2">{e.description}</td>
                <td>{SKILL_LABELS[e.skill]}</td>
                <td>{statusLabel(e.status)}</td>
                <td>{formatRate(e.p_hat, e.ci_low, e.ci_high)}</td>
                <td>{Math.round(e.n_eff)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
