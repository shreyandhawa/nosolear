import { Link } from "@tanstack/react-router";
import { MicStage } from "../../shared/audio/MicStage";
import type { components } from "../../shared/api/schema";
import { Cta, Desk, Label, StatusDot, TitleBlock } from "../../shared/ui/Desk";
import { ctaLink } from "../../shared/ui/styles";
import { useSetup } from "./useSetup";

type Row = components["schemas"]["ReadinessRowOut"];

const Env = ({ lines }: { lines: string[] }) => (
  <pre className="mt-2 bg-fg/12 px-3 py-2 text-[0.9375rem] break-all whitespace-pre-wrap">{lines.join("\n")}</pre>
);

const STATUS_WORD: Record<Row["status"], string> = {
  ready: "ready",
  missing: "missing",
  not_installed: "not installed",
  not_probed: "not checked",
  degraded: "degraded",
};

/** Required parts get their reason and fix; `brief` rows (optional and local parts) get a status word,
 * since their .env line is shown once in the media slot. */
function Rows({ rows, brief = false }: { rows: Row[]; brief?: boolean }) {
  if (brief)
    return (
      <ul className="flex flex-col gap-1.5">
        {rows.map((r) => (
          <li key={r.component} className="flex items-baseline gap-2">
            <StatusDot ok={r.status === "ready"} />
            <span className="font-medium leading-snug">{r.label}</span>
            <span className="ml-auto text-[0.8125rem] text-fg/72">{STATUS_WORD[r.status]}</span>
          </li>
        ))}
      </ul>
    );
  return (
    <ul className="flex flex-col gap-3">
      {rows.map((r) => (
        <li key={r.component} className="grid grid-cols-[0.625rem_1fr] items-baseline gap-x-2">
          <StatusDot ok={r.status === "ready"} />
          <p className="font-medium leading-snug">{r.label}</p>
          <p className="col-start-2 text-[0.8125rem] leading-snug text-fg/72">{r.status === "ready" ? "ready" : r.reason}</p>
          {r.status !== "ready" && r.fix && (
            <p className="col-start-2 text-[0.8125rem] leading-snug">
              Fix: {r.component === "azure_capabilities" ? "press Run check" : r.fix}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}

export function SetupPage() {
  const { readiness, required, coach, local, envLines, coachLines, blocked, probe } = useSetup();
  const open = required.filter((r) => r.status !== "ready").length;
  return (
    <Desk
      stateKey={probe.data ? "checked" : "setup"}
      title={
        <TitleBlock
          step="Setup"
          sub={
            readiness.isPending
              ? "Loading…"
              : readiness.data && (blocked ? "Recording opens once Azure Speech is ready." : "Nothing blocks recording.")
          }
        >
          {readiness.data && (open ? `${open} not ready` : "Ready")}
        </TitleBlock>
      }
      media={
        (envLines.length > 0 || coachLines.length > 0) && (
          <>
            <Label>Add to .env at the repo root, then restart the server</Label>
            {envLines.length > 0 && <Env lines={envLines} />}
            {coachLines.length > 0 && <Env lines={["# optional: the coach", ...coachLines]} />}
          </>
        )
      }
      text={
        readiness.isError ? (
          <p role="alert">Couldn't load readiness. Is the API running?</p>
        ) : (
          readiness.data && (
            <>
              <p>
                <b>Azure Speech is required.</b> It scores your sounds and speaks the model voice. F0 is free and never bills,
                though signup asks for a card and phone.
              </p>
            </>
          )
        )
      }
      stage={<MicStage state="idle" hint={blocked ? "Recording opens after setup" : "Ready to record"} />}
      card={
        <>
          <Label>Azure Speech, required</Label>
          <Rows rows={required} />
          <div className="mt-5">
            <Label>Anthropic coach, optional</Label>
            <Rows rows={coach} brief />
          </div>
          {local.length > 0 && (
            <div className="mt-5">
              <Label>On this machine</Label>
              <Rows rows={local} brief />
            </div>
          )}
        </>
      }
      note={
        probe.isError ? (
          <p role="alert">{probe.error.message}</p>
        ) : probe.data ? (
          <>
            <Label>Check</Label>
            <ul className="flex flex-col gap-1.5 text-[0.9375rem]">
              {probe.data.outcomes.map((o) => (
                <li key={o.adapter} className="flex items-start gap-2">
                  <span className="mt-2">
                    <StatusDot ok={o.ok} />
                  </span>
                  <span>
                    {o.adapter}: {o.message}
                  </span>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <>
            <p>
              <b>The Anthropic coach is optional.</b> It writes personal fixes and scores On the spot and Articulate, for about
              $0.20 a month on Haiku or $7 on Opus. Without it, feedback uses written templates.
            </p>
            <p className="mt-2 text-fg/72">The check makes a few paid calls to Azure, within your caps.</p>
          </>
        )
      }
      cta={
        blocked || !readiness.data ? (
          <Cta onClick={() => probe.mutate()} disabled={probe.isPending}>
            {probe.isPending ? "Checking…" : "Run check"}
          </Cta>
        ) : (
          <Link to="/" className={ctaLink}>
            {coachLines.length > 0 ? "Continue without it" : "Continue"}
          </Link>
        )
      }
    />
  );
}
