import { render, screen } from "@testing-library/react";
import { feedback } from "../../test/fixtures";
import type { components } from "../../shared/api/schema";
import { FeedbackSlots } from "./DailyPage";

type Item = components["schemas"]["FeedbackItemOut"];
const base = feedback.skills[0].item as Item;
const skill = (item: Partial<Item>) =>
  ({ skill: "on_the_spot", state: "fix", item: { ...base, ...item } }) as Parameters<typeof FeedbackSlots>[0];

test("a fix with no word is titled by its description, and an empty text slot shows nothing", () => {
  const slots = FeedbackSlots(
    skill({
      error_key: "prosody.monotone",
      description: "Pitch stays flat instead of rising and falling",
      word: null,
      model_text: null,
    }),
  );
  render(<>{slots.title}{slots.text}</>);
  expect(screen.getByText("Pitch stays flat instead of rising and falling")).toBeInTheDocument();
  expect(screen.queryByText("prosody.monotone")).toBeNull();
  expect(screen.queryByText("Your word")).toBeNull();
  expect(screen.queryByText("Say it like this")).toBeNull();
});

test("each text row shows only when it has a value", () => {
  const slots = FeedbackSlots(skill({ word: null, model_text: "I went" }));
  render(<>{slots.text}</>);
  expect(screen.getByText("Say it like this")).toBeInTheDocument();
  expect(screen.queryByText("Your word")).toBeNull();
});
