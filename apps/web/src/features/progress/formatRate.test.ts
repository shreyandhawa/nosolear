import { formatRate } from "./formatRate";

test.each([
  [0.25, 0.17, 0.34, "25% (17–34%)"],
  [0.004, 0, 0.012, "0% (0–1%)"],
])("formatRate(%s, %s, %s) = %s", (p, lo, hi, out) =>
  expect(formatRate(p, lo, hi)).toBe(out),
);
