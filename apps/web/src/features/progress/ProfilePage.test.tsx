import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { profile } from "../../test/fixtures";
import { renderWithProviders } from "../../test/render";
import { server } from "../../test/server";
import { ProfilePage } from "./ProfilePage";

// The page links to Today; this test renders it without a router.
vi.mock("@tanstack/react-router", () => ({
  Link: ({ to, children, className }: { to: string; children: React.ReactNode; className?: string }) => (
    <a href={to} className={className}>
      {children}
    </a>
  ),
}));

const PROFILE_FIXTURE = profile;

test("shows the empty state", async () => {
  server.use(
    http.get("/api/profile", () =>
      HttpResponse.json({ as_of: null, taxonomy_version: 1, algo_version: 1, entries: [] }),
    ),
  );
  renderWithProviders(<ProfilePage />);
  expect(
    await screen.findByText("No practice data yet. Your baseline will fill this in."),
  ).toBeInTheDocument();
});

test("lists entries in API order with status and rate", async () => {
  server.use(http.get("/api/profile", () => HttpResponse.json(PROFILE_FIXTURE)));
  renderWithProviders(<ProfilePage />);
  const rows = await screen.findAllByRole("row");
  expect(within(rows[1]).getByText("/v/ said as /w/")).toBeInTheDocument();
  expect(within(rows[1]).getByText("Active")).toBeInTheDocument();
  expect(within(rows[1]).getByText("25% (17–34%)")).toBeInTheDocument();
  expect(within(rows[1]).getByText("32")).toBeInTheDocument();
  expect(within(rows[2]).getByText("/θ/ said as /t/")).toBeInTheDocument();
});

test("shows an error when the API fails", async () => {
  server.use(http.get("/api/profile", () => new HttpResponse(null, { status: 500 })));
  renderWithProviders(<ProfilePage />);
  expect(await screen.findByText("Couldn't load your profile. Is the API running?")).toBeInTheDocument();
});
