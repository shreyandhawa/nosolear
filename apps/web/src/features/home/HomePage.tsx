import { Navigate } from "@tanstack/react-router";
import { useHomeTarget } from "./useHomeTarget";

export function HomePage() {
  const { onboarding, target } = useHomeTarget();
  return (
    <main className="mx-auto max-w-2xl p-8">
      <h1 className="text-3xl font-semibold">Nosolear</h1>
      {onboarding.isPending && <p>Loading…</p>}
      {onboarding.isError && <p role="alert">Couldn't reach the API. Is the server running?</p>}
      {target && <Navigate to={target} replace />}
    </main>
  );
}
