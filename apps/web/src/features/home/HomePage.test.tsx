import { render, screen } from "@testing-library/react";
import { HomePage } from "./HomePage";

test("shows the app name and tagline", () => {
  render(<HomePage />);
  expect(screen.getByRole("heading", { name: "Nosolear" })).toBeInTheDocument();
  expect(screen.getByText("Speak daily, get scored, drill your own weak spots.")).toBeInTheDocument();
});
