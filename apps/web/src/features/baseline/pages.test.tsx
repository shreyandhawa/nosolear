import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { baselineReport, baselineSession } from "../../test/fixtures";
import { renderWithProviders } from "../../test/render";
import { server } from "../../test/server";
import { BaselinePage } from "./BaselinePage";
import { ReportPage } from "./ReportPage";

// The pages link and redirect; these tests render them without a router.
vi.mock("@tanstack/react-router", () => ({
  Link: ({ to, children, className }: { to: string; children: React.ReactNode; className?: string }) => (
    <a href={to} className={className}>
      {children}
    </a>
  ),
  Navigate: () => null,
}));

test("the baseline card lists only the current section, with the prompt in the title", async () => {
  server.use(http.get("/api/baseline", () => HttpResponse.json(baselineSession(false, false))));
  renderWithProviders(<BaselinePage />);
  expect(await screen.findByRole("heading", { level: 3, name: "Read aloud" })).toBeInTheDocument();
  const card = screen.getByRole("region", { name: "This step" });
  expect(within(card).getAllByRole("listitem")).toHaveLength(3);
  expect(within(card).queryByText(/Describe a place/)).toBeNull();
  expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Baseline, item 1 of 5");
  expect(screen.getByText("A very good day.", { selector: "p" })).toBeInTheDocument();
});

test("a long prompt moves to the media slot, not the title", async () => {
  const session = baselineSession(false, false);
  session.items[0].recorded = true;
  session.items[1].recorded = true;
  session.items[2].recorded = true;
  session.items[3].recorded = true;
  server.use(http.get("/api/baseline", () => HttpResponse.json(session)));
  renderWithProviders(<BaselinePage />);
  const listen = await screen.findByRole("region", { name: "Listen" });
  expect(within(listen).getByText(/Explain how you would teach/)).toBeInTheDocument();
  expect(within(screen.getByRole("region", { name: "Title" })).queryByText(/Explain how/)).toBeNull();
});

test("the report shows the top error, five ranked errors and a link to Progress", async () => {
  server.use(http.get("/api/baseline", () => HttpResponse.json(baselineSession(true))));
  server.use(http.get("/api/baseline/report", () => HttpResponse.json(baselineReport)));
  renderWithProviders(<ReportPage />);
  const link = await screen.findByRole("link", { name: "See all on Progress" });
  const notes = screen.getByRole("region", { name: "Notes" });
  expect(within(notes).getAllByRole("button")).toHaveLength(5);
  expect(link).toHaveAttribute("href", "/profile");
  const text = screen.getByRole("region", { name: "Instructions" });
  expect(within(text).getByText(/Sounds, Active/)).toBeInTheDocument();
  // The description appears once, in the ranked list; the title holds the phonetic pair.
  expect(screen.getAllByText("/v/ said as /w/")).toHaveLength(1);
});

test("a top error without clips shows no clips label, and the calibration state is left to the API's notes", async () => {
  const report = { ...baselineReport, calibration: "calibrated", items: [{ ...baselineReport.items[0], clips: [] }] };
  server.use(http.get("/api/baseline", () => HttpResponse.json(baselineSession(true))));
  server.use(http.get("/api/baseline/report", () => HttpResponse.json(report)));
  renderWithProviders(<ReportPage />);
  await screen.findByRole("link", { name: "See all on Progress" });
  expect(screen.queryByText("Your clips")).toBeNull();
  expect(screen.queryByText(/Calibration is/)).toBeNull();
});
