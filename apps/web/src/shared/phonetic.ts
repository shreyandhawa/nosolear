/** "sound.sub.θ.t" → ["θ", "t"]; other keys → null. Presentation only. */
export function phoneticPair(errorKey: string): [string, string] | null {
  const parts = errorKey.split(".");
  return parts[0] === "sound" && parts[1] === "sub" && parts.length === 4 ? [parts[2], parts[3]] : null;
}
