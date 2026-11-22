import { fireEvent, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { onboarding } from "../../test/fixtures";
import { renderWithProviders } from "../../test/render";
import { server } from "../../test/server";
import { welcomeSeen } from "../../shared/welcomeSeen";
import { WelcomePage } from "./WelcomePage";

// The page links to Setup; this test renders it without a router.
vi.mock("@tanstack/react-router", () => ({
  Link: ({ to, children, className }: { to: string; children: React.ReactNode; className?: string }) => (
    <a href={to} className={className}>
      {children}
    </a>
  ),
}));

test("lists the parts, explains the selected one and starts setup", async () => {
  localStorage.clear();
  server.use(http.get("/api/onboarding", () => HttpResponse.json(onboarding("readiness"))));
  renderWithProviders(<WelcomePage />);
  expect(screen.getByRole("link", { name: "Start setup" })).toHaveAttribute("href", "/setup");
  fireEvent.click(screen.getByRole("button", { name: "Today" }));
  expect(screen.getByText(/Speak for 60 seconds/)).toBeInTheDocument();
  expect(welcomeSeen()).toBe(true);
});
