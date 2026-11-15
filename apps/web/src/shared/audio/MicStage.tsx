import { lazy, Suspense, useEffect, useRef, useState, type CSSProperties } from "react";
import { ARC_R, HEAD, SLATS, svgY, VIEW, VIEW_BOX } from "./micGeometry";

const MicScene = lazy(() => import("./MicScene"));

export type MicState = "idle" | "ready" | "recording" | "analyzing" | "done" | "error";

const SPOKEN: Record<MicState, string> = {
  idle: "",
  ready: "Ready to record",
  recording: "On air",
  analyzing: "Analyzing",
  done: "Done",
  error: "Recording stopped with an error",
};

function useReducedMotion() {
  const query = "(prefers-reduced-motion: reduce)";
  const [reduced, setReduced] = useState(() => globalThis.matchMedia?.(query).matches ?? false);
  useEffect(() => {
    const m = globalThis.matchMedia?.(query);
    const on = () => setReduced(m.matches);
    m?.addEventListener("change", on);
    return () => m?.removeEventListener("change", on);
  }, []);
  return reduced;
}

// The button is the circle the arc draws around the head.
const top = (VIEW.cy + VIEW.h / 2 - HEAD.y - ARC_R) / VIEW.h;
const buttonBox: CSSProperties = {
  left: `${50 - (ARC_R / VIEW.w) * 100}%`,
  top: `${top * 100}%`,
  width: `${((2 * ARC_R) / VIEW.w) * 100}%`,
  height: `${((2 * ARC_R) / VIEW.h) * 100}%`,
};
/** The time arc: clockwise from the top of the head's circle, `filled` of the way round. */
function arc(filled: number) {
  const cy = svgY(HEAD.y);
  const a = Math.min(filled, 0.9999) * 2 * Math.PI;
  const x = ARC_R * Math.sin(a);
  const y = cy - ARC_R * Math.cos(a);
  return `M 0 ${cy - ARC_R} A ${ARC_R} ${ARC_R} 0 ${a > Math.PI ? 1 : 0} 1 ${x} ${y}`;
}

const haloCentre = `${((VIEW.cy + VIEW.h / 2 - HEAD.y) / VIEW.h) * 100}%`;

/** The microphone on the Ink stage. It is the record control: a real button over a decorative
 * canvas. The halo is the level meter while recording. */
export function MicStage({
  state,
  progress = 0,
  elapsed = 0,
  maxSeconds = 0,
  getLevel,
  onPress,
  hint,
}: {
  state: MicState;
  /** The analysis job's real progress, 0 to 1. */
  progress?: number;
  elapsed?: number;
  maxSeconds?: number;
  getLevel?: () => number;
  onPress?: () => void;
  hint: string;
}) {
  const halo = useRef<HTMLDivElement>(null);
  const level = useRef(0);
  const reduced = useReducedMotion();
  const [scene, setScene] = useState<"loading" | "ready" | "failed">("loading");

  useEffect(() => {
    const el = halo.current;
    level.current = 0;
    el?.style.setProperty("--level", "0");
    if (state !== "recording" || !getLevel) return;
    let raf = 0;
    const tick = () => {
      let v = Math.min(1, getLevel() * 5);
      if (reduced) v = Math.round(v * 4) / 4; // static steps: still a meter, no smooth motion
      level.current = v;
      el?.style.setProperty("--level", v.toFixed(3));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [state, getLevel, reduced]);

  const lit = state === "analyzing" ? Math.round(progress * SLATS.length) : 0;
  const filled = state === "recording" && maxSeconds > 0 ? Math.min(1, elapsed / maxSeconds) : 0;
  return (
    <div className="mic" data-state={state} data-reduced={reduced || undefined}>
      <div className="mic-box" data-scene={scene}>
        <div ref={halo} className="mic-halo" style={{ top: haloCentre }} aria-hidden />
        <Silhouette lit={lit} state={state} />
        {scene !== "failed" && (
          <Suspense fallback={null}>
            <MicScene
              state={state}
              progress={state === "analyzing" ? progress : 0}
              level={level}
              reduced={reduced}
              onReady={() => setScene("ready")}
              onFail={() => setScene("failed")}
            />
          </Suspense>
        )}
        <svg viewBox={VIEW_BOX} className="pointer-events-none absolute inset-0 size-full" aria-hidden>
          {state === "recording" && filled > 0 && <path className="mic-arc" d={arc(filled)} />}
        </svg>
        <button
          type="button"
          className="mic-button"
          style={buttonBox}
          aria-pressed={state === "recording"}
          aria-label={!onPress ? "Microphone, not available here" : state === "recording" ? "Stop recording" : "Start recording"}
          aria-keyshortcuts="Space"
          disabled={!onPress}
          onClick={onPress}
        />
      </div>
      <p className="mic-hint">
        {state === "recording" && <span className="mic-onair">On air</span>}
        {hint}
      </p>
      <p className="sr-only-live" aria-live="polite">
        {SPOKEN[state]}
      </p>
    </div>
  );
}

/** The flat microphone shown until the 3D scene is ready, and whenever WebGL is unavailable. */
function Silhouette({ lit, state }: { lit: number; state: MicState }) {
  const lamp = state === "recording" ? "var(--color-onair)" : state === "ready" ? "var(--color-paper)" : "none";
  return (
    <svg viewBox={VIEW_BOX} className="mic-flat absolute inset-0 size-full" aria-hidden>
      <g fill="color-mix(in oklch, var(--color-paper) 16%, transparent)">
        <rect x={-0.92} y={svgY(0.16)} width={1.84} height={0.16} rx={0.05} />
        <rect x={-0.06} y={svgY(1.35)} width={0.12} height={1.19} />
        <rect x={-0.17} y={svgY(1.62)} width={0.34} height={0.27} rx={0.03} />
        <rect x={-HEAD.r} y={svgY(HEAD.y + HEAD.half)} width={HEAD.r * 2} height={HEAD.half * 2} rx={HEAD.r} />
      </g>
      <path
        d={`M -0.8 ${svgY(2.6)} V ${svgY(2.15)} A 0.8 0.8 0 0 0 0.8 ${svgY(2.15)} V ${svgY(2.6)}`}
        fill="none"
        stroke="color-mix(in oklch, var(--color-paper) 22%, transparent)"
        strokeWidth={0.1}
      />
      {SLATS.map((s, i) => (
        <line
          key={s.y}
          x1={-s.r}
          x2={s.r}
          y1={svgY(s.y)}
          y2={svgY(s.y)}
          strokeWidth={0.05}
          strokeLinecap="round"
          stroke={i < lit ? "var(--color-phosphor)" : "color-mix(in oklch, var(--color-paper) 30%, transparent)"}
        />
      ))}
      {lamp !== "none" && <circle cx={0} cy={svgY(1.5)} r={0.05} fill={lamp} />}
    </svg>
  );
}
