import {
  createRootRoute,
  createRoute,
  createRouter,
  Link,
  Outlet,
} from "@tanstack/react-router";
import { HomePage } from "../features/home/HomePage";
import { ProfilePage } from "../features/progress/ProfilePage";

function RootLayout() {
  return (
    <>
      <nav className="flex gap-4 border-b border-slate-200 px-8 py-3 text-sm">
        <Link to="/">Home</Link>
        <Link to="/profile">Profile</Link>
      </nav>
      <Outlet />
    </>
  );
}

export function createAppRouter() {
  const rootRoute = createRootRoute({ component: RootLayout });
  const homeRoute = createRoute({ getParentRoute: () => rootRoute, path: "/", component: HomePage });
  const profileRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/profile",
    component: ProfilePage,
  });
  return createRouter({ routeTree: rootRoute.addChildren([homeRoute, profileRoute]) });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createAppRouter>;
  }
}
