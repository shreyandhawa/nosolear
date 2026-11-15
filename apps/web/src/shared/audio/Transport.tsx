import { useEffect, useState } from "react";
import type { Take } from "./useTake";

// The tabular colon sets wide; a proportional one keeps "0:42" tight.
const clock = (s: number) => (
  <>
    {Math.floor(s / 60)}
    <span className="[font-variant-numeric:normal]">:</span>
    {String(Math.floor(s % 60)).padStart(2, "0")}
  </>
);

/** Elapsed of the limit, the input level and the microphone picker. */
export function Transport({ take }: { take: Take }) {
  const [mics, setMics] = useState<MediaDeviceInfo[]>([]);
  const recording = take.phase === "recording";
  useEffect(() => {
    // Labels appear once the page has had microphone access; until then the browser's default is used.
    void navigator.mediaDevices
      ?.enumerateDevices()
      .then((all) => setMics(all.filter((d) => d.kind === "audioinput" && d.label)));
  }, [recording]);
  return (
    <div className="flex flex-col gap-3">
      <p className="num text-[2rem] leading-none font-medium">
        {clock(take.elapsed)}
        <span className="text-ink/70"> of {take.maxSeconds} s</span>
      </p>
      <div
        role="meter"
        aria-label="Input level"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(Math.min(1, take.level * 4) * 100)}
        className="h-1.5 w-full overflow-hidden rounded-full bg-ink/12"
      >
        <div className="h-full rounded-full bg-ink" style={{ width: `${Math.min(1, take.level * 4) * 100}%` }} />
      </div>
      {mics.length > 1 && (
        <label className="flex items-center gap-2 text-[0.8125rem] text-ink/70">
          Microphone
          <select
            className="min-w-0 flex-1 rounded border border-ink/30 bg-transparent px-2 py-1 text-ink"
            value={take.deviceId ?? ""}
            onChange={(e) => take.setDeviceId(e.target.value || undefined)}
            disabled={recording}
          >
            <option value="">Default</option>
            {mics.map((m) => (
              <option key={m.deviceId} value={m.deviceId}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
      )}
    </div>
  );
}
