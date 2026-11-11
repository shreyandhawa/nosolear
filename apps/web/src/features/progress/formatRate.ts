const pct = (x: number) => Math.round(x * 100);

export function formatRate(p: number, low: number, high: number): string {
  return `${pct(p)}% (${pct(low)}–${pct(high)}%)`;
}
