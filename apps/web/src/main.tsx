import { RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { AppProviders } from "./app/AppProviders";
import { createAppRouter } from "./app/router";
import "./index.css";

async function start() {
  // Dev only: `?mock=today` (or setup, calibration, baseline, report, progress) serves the tests'
  // fixtures. The branch and its import are removed from production builds.
  const scenario = new URLSearchParams(location.search).get("mock");
  if (import.meta.env.DEV && scenario) (await import("./dev/mock")).install(scenario);

  const router = createAppRouter();
  const root = document.getElementById("root");
  if (!root) throw new Error("Missing #root element");
  createRoot(root).render(
    <StrictMode>
      <AppProviders>
        <RouterProvider router={router} />
      </AppProviders>
    </StrictMode>,
  );
}

void start();
