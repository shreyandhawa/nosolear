import { createRootRoute, createRoute, createRouter, Outlet } from "@tanstack/react-router";
import { HomePage } from "../features/home/HomePage";

export function createAppRouter() {
  const rootRoute = createRootRoute({ component: Outlet });
  const homeRoute = createRoute({ getParentRoute: () => rootRoute, path: "/", component: HomePage });
  return createRouter({ routeTree: rootRoute.addChildren([homeRoute]) });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createAppRouter>;
  }
}
