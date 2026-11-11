import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { components } from "../../shared/api/schema";
import { renderWithProviders } from "../../test/render";
import { server } from "../../test/server";
import { ProfilePage } from "./ProfilePage";

const PROFILE_FIXTURE: components["schemas"]["ProfileOut"] = {
  as_of: "2026-11-10T12:00:00Z",
  taxonomy_version: 1,
  algo_version: 1,
  entries: [
    {
      error_key: "sound.sub.v.w",
      description: "/v/ said as /w/",
      family: "sound",
      skill: "sounds",
      impact: 3,
      status: "active",
      p_hat: 0.25,
      ci_low: 0.17,
      ci_high: 0.34,
      n_eff: 31.6,
      priority: 0.75,
      last_seen_at: "2026-11-10T12:00:00Z",
    },
    {
      error_key: "sound.sub.th.t",
      description: "/θ/ said as /t/",
      family: "sound",
      skill: "sounds",
      impact: 2,
      status: "unknown",
      p_hat: 0.1,
      ci_low: 0.04,
      ci_high: 0.2,
      n_eff: 3.2,
      priority: 0.2,
      last_seen_at: "2026-11-09T12:00:00Z",
    },
  ],
};

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
