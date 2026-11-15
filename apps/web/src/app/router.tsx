import { createRootRoute, createRoute, createRouter, Link, Outlet } from "@tanstack/react-router";
import { BaselinePage } from "../features/baseline/BaselinePage";
import { CalibrationPage } from "../features/calibration/CalibrationPage";
import { DailyPage } from "../features/daily/DailyPage";
import { HomePage } from "../features/home/HomePage";
import { ProfilePage } from "../features/progress/ProfilePage";
import { SetupPage } from "../features/setup/SetupPage";

function RootLayout() {
  return (
    <>
      <nav className="flex gap-4 border-b border-slate-200 px-8 py-3 text-sm">
        <Link to="/">Home</Link>
        <Link to="/setup">Setup</Link>
        <Link to="/calibration">Calibration</Link>
        <Link to="/baseline">Baseline</Link>
        <Link to="/today">Today</Link>
        <Link to="/profile">Progress</Link>
      </nav>
      <Outlet />
    </>
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
