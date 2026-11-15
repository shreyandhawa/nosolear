import { Link } from "@tanstack/react-router";
import { MicStage } from "../../shared/audio/MicStage";
import { Cta, Desk, Label, StatusDot, TitleBlock } from "../../shared/ui/Desk";
import { ctaLink } from "../../shared/ui/styles";
import { useSetup } from "./useSetup";

export function SetupPage() {
  const { readiness, envLines, blocked, probe } = useSetup();
  const rows = readiness.data?.rows ?? [];
  const open = rows.filter((r) => r.status !== "ready").length;
  return (
    <Desk
      stateKey={probe.data ? "checked" : "setup"}
      title={
        <TitleBlock
          step="Setup"
          sub={
            readiness.isPending
              ? "Loading…"
              : readiness.data && (blocked ? "Recording opens once the required rows are fixed." : "Nothing blocks recording.")
          }
        >
          {readiness.data && (open ? `${open} not ready` : "Ready")}
        </TitleBlock>
      }
      media={
        envLines.length > 0 && (
          <>
            <Label>Still missing in .env</Label>
            <pre className="rounded bg-ink/6 px-3 py-2 text-[0.9375rem] break-all whitespace-pre-wrap">{envLines.join("\n")}</pre>
          </>
        )
      }
      text={
        envLines.length > 0 ? (
          <p>Add them to the .env file at the repo root, then restart the server.</p>
        ) : (
          readiness.isError && <p role="alert">Couldn't load readiness. Is the API running?</p>
        )
      }
      stage={<MicStage state="idle" hint={blocked ? "Recording opens after setup" : "Ready to record"} />}
      card={
        <>
          <Label>Readiness</Label>
          <ul className="flex flex-col gap-3">
            {rows.map((r) => (
              <li key={r.component} className="grid grid-cols-[0.625rem_1fr] items-baseline gap-x-2">
                <StatusDot ok={r.status === "ready"} />
                <p className="font-medium leading-snug">{r.label}</p>
                <p className="col-start-2 text-[0.8125rem] leading-snug text-ink/70">
                  {r.status === "ready" ? "ready" : r.reason}
                </p>
                {r.status !== "ready" && r.fix && (
                  <p className="col-start-2 text-[0.8125rem] leading-snug">
                    Fix: {r.component === "azure_capabilities" ? "press Run check" : r.fix}
                  </p>
                )}
              </li>
            ))}
          </ul>
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
          <p>The check makes a few paid calls to Azure, within your caps.</p>
        )
      }
      cta={
        blocked || !readiness.data ? (
          <Cta onClick={() => probe.mutate()} disabled={probe.isPending}>
            {probe.isPending ? "Checking…" : "Run check"}
          </Cta>
        ) : (
          <Link to="/" className={ctaLink}>
            Continue
          </Link>
        )
      }
    />
  );
}
