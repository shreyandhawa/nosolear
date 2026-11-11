import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

export function AppProviders({
  children,
  queryClient: provided,
}: {
  children: ReactNode;
  queryClient?: QueryClient;
}) {
  const [created] = useState(() => new QueryClient());
  return <QueryClientProvider client={provided ?? created}>{children}</QueryClientProvider>;
}
