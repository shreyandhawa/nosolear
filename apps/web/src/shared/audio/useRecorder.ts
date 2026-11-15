import { useCallback, useEffect, useRef, useState } from "react";
import { encodeWav, joinChunks, resample, rms } from "./wav";

export type RecorderState = "idle" | "starting" | "recording" | "recorded" | "denied" | "error";

// Copies each 128-sample block to the page; outputs silence.
const TAP = `class Tap extends AudioWorkletProcessor {
  process(inputs) { const ch = inputs[0] && inputs[0][0]; if (ch) this.port.postMessage(ch.slice(0)); return true; }
}
registerProcessor("nosolear-tap", Tap);`;

type Live = {
  ctx: AudioContext;
  stream: MediaStream;
  chunks: Float32Array[];
  timer: number;
  level: number;
};

function isTyping(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && target.closest("button, input, textarea, select") !== null;
}

/** Records from the microphone into a 16 kHz mono WAV held in memory. Space toggles. */
export function useRecorder({ maxSeconds, keyboard = true }: { maxSeconds: number; keyboard?: boolean }) {
  const [state, setState] = useState<RecorderState>("idle");
  const [level, setLevel] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [wav, setWav] = useState<Uint8Array | null>(null);
  const live = useRef<Live | null>(null);

  const release = (l: Live) => {
    window.clearInterval(l.timer);
    l.stream.getTracks().forEach((t) => t.stop());
    void l.ctx.close();
  };

  const stop = useCallback(() => {
    const l = live.current;
    if (!l) return;
    live.current = null;
    release(l);
    setWav(encodeWav(resample(joinChunks(l.chunks), l.ctx.sampleRate)));
    setLevel(0);
    setState("recorded");
  }, []);

  const start = useCallback(async () => {
    if (live.current) return;
    setState("starting");
    setWav(null);
    setElapsed(0);
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: false },
      });
    } catch (e) {
      setState(e instanceof DOMException && e.name === "NotAllowedError" ? "denied" : "error");
      return;
    }
    try {
      const ctx = new AudioContext();
      const url = URL.createObjectURL(new Blob([TAP], { type: "text/javascript" }));
      try {
        await ctx.audioWorklet.addModule(url);
      } finally {
        URL.revokeObjectURL(url);
      }
      const node = new AudioWorkletNode(ctx, "nosolear-tap");
      const l: Live = { ctx, stream, chunks: [], timer: 0, level: 0 };
      node.port.onmessage = (e: MessageEvent<Float32Array>) => {
        l.chunks.push(e.data);
        l.level = rms(e.data);
      };
      ctx.createMediaStreamSource(stream).connect(node);
      node.connect(ctx.destination);
      const began = performance.now();
      l.timer = window.setInterval(() => {
        const seconds = (performance.now() - began) / 1000;
        setElapsed(seconds);
        setLevel(l.level);
        if (seconds >= maxSeconds) stop();
      }, 100);
      live.current = l;
      setState("recording");
    } catch {
      stream.getTracks().forEach((t) => t.stop());
      setState("error");
    }
  }, [maxSeconds, stop]);

  const toggle = useCallback(() => {
    if (live.current) stop();
    else void start();
  }, [start, stop]);

  useEffect(() => {
    if (!keyboard) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.code !== "Space" || e.repeat || isTyping(e.target)) return;
      e.preventDefault();
      toggle();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [keyboard, toggle]);

  useEffect(
    () => () => {
      if (live.current) release(live.current);
      live.current = null;
    },
    [],
  );

  const reset = useCallback(() => {
    setWav(null);
    setElapsed(0);
    setState("idle");
  }, []);

  return { state, level, elapsed, wav, start, stop, toggle, reset };
}
