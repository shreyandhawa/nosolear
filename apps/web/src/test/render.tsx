import { QueryClient } from "@tanstack/react-query";
import { render, renderHook } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { AppProviders } from "../app/AppProviders";

export function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<AppProviders queryClient={queryClient}>{ui}</AppProviders>);
}

export function renderHookWithProviders<T>(hook: () => T) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderHook(hook, {
    wrapper: ({ children }: { children: ReactNode }) => (
      <AppProviders queryClient={queryClient}>{children}</AppProviders>
    ),
  });
}
