import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { readiness } from "../../test/fixtures";
import { renderWithProviders } from "../../test/render";
import { server } from "../../test/server";
import { SetupPage } from "./SetupPage";

vi.mock("@tanstack/react-router", () => ({
  Link: ({ to, children }: { to: string; children: React.ReactNode }) => <a href={to}>{children}</a>,
}));

test("local parts that are all ready fold into one line, so the card stays short", async () => {
  const body = readiness(true);
  const local = (component: string, label: string) => ({ ...body.rows[0], component, label });
  body.rows.push(local("transcriber", "Transcriber"), local("phone_probe", "Phone probe"));
  server.use(http.get("/api/readiness", () => HttpResponse.json(body)));
  renderWithProviders(<SetupPage />);
  const card = await screen.findByRole("region", { name: "This step" });
  expect(await within(card).findByText("Transcriber, Phone probe: ready")).toBeInTheDocument();
});
