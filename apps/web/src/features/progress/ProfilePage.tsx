import { Link } from "@tanstack/react-router";
import { MicStage } from "../../shared/audio/MicStage";
import type { components } from "../../shared/api/schema";
import { Desk, Label, TitleBlock } from "../../shared/ui/Desk";
import { ctaLink } from "../../shared/ui/styles";
import { formatRate } from "./formatRate";
import { statusLabel } from "../../shared/statusLabel";
import { useProfile } from "./useProfile";

const SKILL_LABELS: Record<components["schemas"]["ProfileEntryOut"]["skill"], string> = {
  sounds: "Sounds",
  on_the_spot: "On the spot",
  articulate: "Articulate",
};

export function ProfilePage() {
  const { data, isPending, isError } = useProfile();
  const active = data?.entries.filter((e) => e.status === "active").length ?? 0;

  return (
    <Desk
      stateKey="progress"
      title={
        <TitleBlock
          step="Progress"
          sub={data && data.entries.length > 0 ? `active, of ${data.entries.length} errors tracked` : undefined}
        >
          {data && data.entries.length > 0 ? active : null}
        </TitleBlock>
      }
      text={
        <>
          {isPending && <p className="text-fg/72">Loading…</p>}
          {isError && <p role="alert">Couldn't load your profile. Is the API running?</p>}
          {data && data.entries.length === 0 && <p className="text-fg/72">No practice data yet. Your baseline will fill this in.</p>}
        </>
      }
      media={
        data &&
        data.entries.length > 0 && (
          <table className="w-full text-left align-top text-[0.875rem] [&_td]:py-2 [&_td]:pr-3 [&_td]:align-top [&_th]:pr-3">
            <thead className="text-fg/72">
              <tr>
                <th className="pb-1 font-medium">Problem</th>
                <th className="pb-1 font-medium">Status</th>
                <th className="pb-1 font-medium">Miss rate</th>
                <th className="pb-1 font-medium">Evidence</th>
              </tr>
            </thead>
            <tbody>
              {data.entries.map((e) => (
                <tr key={e.error_key} className="border-t border-fg/10">
                  <td>
                    <span className="block font-display text-[1rem]">{e.description}</span>
                    <span className="text-fg/72">{SKILL_LABELS[e.skill]}</span>
                  </td>
                  <td>{statusLabel(e.status)}</td>
                  <td className="num whitespace-nowrap">{formatRate(e.p_hat, e.ci_low, e.ci_high)}</td>
                  <td className="num">{Math.round(e.n_eff)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      }
      stage={<MicStage state="idle" hint="Practice happens in today's session" />}
      card={
        <>
          <Label>About this page</Label>
          <p>Each error's miss rate, with its range, and how much evidence stands behind it.</p>
        </>
      }
      cta={
        <Link to="/today" className={ctaLink}>
          Open today's session
        </Link>
      }
    />
  );
}
