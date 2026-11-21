import { createRootRoute, createRoute, createRouter, Link, Outlet, useLocation } from "@tanstack/react-router";
import { BaselinePage } from "../features/baseline/BaselinePage";
import { CalibrationPage } from "../features/calibration/CalibrationPage";
import { DailyPage } from "../features/daily/DailyPage";
import { HomePage } from "../features/home/HomePage";
import { ProfilePage } from "../features/progress/ProfilePage";
import { SetupPage } from "../features/setup/SetupPage";
import { StatusDot } from "../shared/ui/Desk";
import { useNav } from "./useNav";

const TRAIL = [
  { step: "readiness", label: "Setup", to: "/setup" },
  { step: "calibration", label: "Calibration", to: "/calibration" },
  { step: "baseline", label: "Baseline", to: "/baseline" },
  { step: "report", label: "Report", to: "/baseline" },
] as const;

const link = "py-1 text-fg/72 transition-colors duration-150 hover:text-fg [&.active]:text-fg [&.active]:font-semibold";

function RootLayout() {
  const nav = useNav();
  const at = TRAIL.findIndex((t) => t.step === nav.step);
  const path = useLocation({ select: (l) => l.pathname });
  return (
    <div className="app">
      <nav aria-label="Main" className="flex h-15 items-center gap-10 border-b border-fg/12 px-8 text-[0.9375rem]">
        <Link to="/" className="font-display text-[1.375rem] leading-none">
          Nosolear
        </Link>
        {nav.firstRun ? (
          <ol aria-label="First run" className="flex items-center gap-7">
            {TRAIL.map((t, i) => (
              <li key={t.step} className="flex items-center gap-2">
                {/* Filled when the step is done or is the page you are on. */}
                <StatusDot ok={i < at || t.to === path} />
                <Link to={t.to} className={link} aria-current={i === at ? "step" : undefined}>
                  {t.label}
                </Link>
              </li>
            ))}
          </ol>
        ) : (
          <ul className="flex items-center gap-7">
            <li>
              <Link to="/today" className={link}>
                Today
              </Link>
            </li>
            <li>
              <Link to="/profile" className={link}>
                Progress
              </Link>
            </li>
            <li>
              <Link to="/baseline" className={link}>
                Baseline
              </Link>
            </li>
            <li>
              <Link to="/setup" className={link}>
                Setup
              </Link>
            </li>
          </ul>
        )}
        <p className="ml-auto flex min-w-0 items-center gap-2 text-[0.8125rem] text-fg/72">
          {!nav.firstRun && (
            <span className="flex shrink-0 items-center gap-1.5">
              <StatusDot ok={nav.ready} />
              {nav.ready ? "Ready" : "Not ready"}
            </span>
          )}
          {nav.usage && (
            <span className="truncate" title={nav.usage}>
              {nav.usage}
            </span>
          )}
        </p>
      </nav>
      <Outlet />
    </div>
  );
}

export function createAppRouter() {
  const rootRoute = createRootRoute({ component: RootLayout });
  const parent = () => rootRoute;
  return createRouter({
    routeTree: rootRoute.addChildren([
      createRoute({ getParentRoute: parent, path: "/", component: HomePage }),
      createRoute({ getParentRoute: parent, path: "/setup", component: SetupPage }),
      createRoute({ getParentRoute: parent, path: "/calibration", component: CalibrationPage }),
      createRoute({ getParentRoute: parent, path: "/baseline", component: BaselinePage }),
      createRoute({ getParentRoute: parent, path: "/today", component: DailyPage }),
      createRoute({ getParentRoute: parent, path: "/profile", component: ProfilePage }),
    ]),
  });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createAppRouter>;
  }
}
