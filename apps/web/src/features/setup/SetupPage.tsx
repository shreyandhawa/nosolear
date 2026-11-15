import { Link } from "@tanstack/react-router";
import { useSetup } from "./useSetup";

export function SetupPage() {
  const { readiness, envLines, blocked, probe } = useSetup();
  return (
    <main className="mx-auto max-w-4xl p-8">
      <h1 className="text-2xl font-semibold">Setup</h1>
      {readiness.isPending && <p>Loading…</p>}
      {readiness.isError && <p role="alert">Couldn't load readiness. Is the API running?</p>}
      {readiness.data && (
        <table className="mt-4 w-full text-left text-sm">
          <thead>
            <tr>
              <th>Component</th>
              <th>Status</th>
              <th>Reason</th>
              <th>Fix</th>
            </tr>
          </thead>
          <tbody>
            {readiness.data.rows.map((r) => (
              <tr key={r.component}>
                <td>{r.label}</td>
                <td>{r.status.replace("_", " ")}</td>
                <td>{r.reason}</td>
                <td>{r.fix}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {envLines.length > 0 && (
        <section className="mt-4">
          <h2 className="font-semibold">Still missing in .env</h2>
          <pre>{envLines.join("\n")}</pre>
          <p>Add them to the .env file at the repo root, then restart the server.</p>
        </section>
      )}
      <p className="mt-4">
        <button type="button" className="rounded border px-4 py-2" onClick={() => probe.mutate()} disabled={probe.isPending}>
          {probe.isPending ? "Checking…" : "Run check"}
        </button>{" "}
        The check makes a few paid calls to Azure, within your caps.
      </p>
      {probe.isError && <p role="alert">{probe.error.message}</p>}
      {probe.data && (
        <ul className="mt-2">
          {probe.data.outcomes.map((o) => (
            <li key={o.adapter}>
              {o.ok ? "ok" : "failed"} {o.adapter}: {o.message}
            </li>
          ))}
        </ul>
      )}
      {!blocked && readiness.data && (
        <p className="mt-4">
          Ready. <Link to="/">Continue</Link>
        </p>
      )}
    </main>
  );
}
