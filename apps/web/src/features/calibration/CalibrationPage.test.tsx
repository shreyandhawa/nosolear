import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { calibrationRun } from "../../test/fixtures";
import { renderWithProviders } from "../../test/render";
import { server } from "../../test/server";
import { CalibrationPage } from "./CalibrationPage";

vi.mock("@tanstack/react-router", () => ({
  Link: ({ to, children }: { to: string; children: React.ReactNode }) => <a href={to}>{children}</a>,
  Navigate: () => null,
}));

test("a finished run names the detectors that stay off, in phones, with the full table folded away", async () => {
  const run = calibrationRun("done", [true]);
  run.results.push({ ...run.results[0], detector: "phone_probe", enabled: false, hit_rate: 0.5, false_alarm_rate: 0.8 });
  server.use(http.get("/api/calibration", () => HttpResponse.json(run)));
  renderWithProviders(<CalibrationPage />);
  const text = await screen.findByRole("region", { name: "Instructions" });
  expect(within(text).getByRole("listitem").textContent).toBe("/v/ as /w/ (Probe): 50% hits, 80% false alarms");
  expect(within(text).getByText(`All ${run.results.length} detectors`)).toBeInTheDocument();
  expect(within(text).queryByText("sound.sub.v.w")).toBeNull();
});
