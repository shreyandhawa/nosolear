// Dev only: `?mock=<scenario>` serves the hook tests' fixtures so every screen state can be seen
// without provider keys. main.tsx imports this behind `import.meta.env.DEV`, so it never ships.
import * as f from "../test/fixtures";

type Reply = unknown | Response;

const STEP: Record<string, string> = {
  setup: "readiness",
  calibration: "calibration",
  baseline: "baseline",
  report: "report",
  today: "daily_plan",
  progress: "daily_plan",
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

export function install(scenario: string) {
  let probed = scenario !== "setup";
  let calibration: object | null = f.calibrationRun("running", [true, false]);
  let baseline: object | null = f.baselineSession(scenario === "report", scenario === "report");
  let polls = 0;
  let job = "analyze";

  const routes: Record<string, (body: unknown) => Reply> = {
    "GET /api/onboarding": () => f.onboarding(STEP[scenario] ?? "daily_plan"),
    "GET /api/readiness": () => f.readiness(probed),
    "POST /api/readiness/probe": () => {
      probed = true;
      return f.probeRun;
    },
    "GET /api/calibration": () => calibration ?? json({ code: "no_calibration", message: "none" }, 404),
    "POST /api/calibration": () => (calibration = f.calibrationRun("running", [true, false])),
    "POST /api/calibration/finish": () => {
      job = "calibrate";
      polls = 0;
      return json({ job_id: "j1" }, 202);
    },
    "GET /api/baseline": () => baseline,
    "POST /api/baseline": () => baseline,
    "POST /api/baseline/complete": () => {
      baseline = f.baselineSession(true);
      return f.baselineReport;
    },
    "GET /api/baseline/report": () => f.baselineReport,
    "GET /api/plan/today": () => f.plan,
    "POST /api/plan/today/session": () => json(f.dailySession, 201),
    "GET /api/jobs/j1": () => {
      polls += 1;
      const progress = Math.min(1, polls * 0.2);
      if (job === "calibrate" && progress >= 1) calibration = f.calibrationRun("done", [true, true]);
      return { ...f.analyzeJob(progress >= 1 ? "done" : "running", progress), kind: job };
    },
    "POST /api/sessions/s1/feedback": () => f.feedback,
    "POST /api/sessions/s1/complete": () => f.completed,
    "GET /api/profile": () => f.profile,
    "POST /api/model-voice": () => ({ clip_id: "0".repeat(64), duration_ms: 900 }),
  };

  const real = globalThis.fetch.bind(globalThis);
  globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const req = input instanceof Request ? input : new Request(input, init);
    const path = new URL(req.url).pathname;
    if (!path.startsWith("/api/")) return real(input, init);
    const upload = /^\/api\/attempts\/([^/]+)\/recording$/.exec(path);
    if (upload && req.method === "POST") {
      if (scenario === "calibration") calibration = f.calibrationRun("running", [true, true]);
      if (scenario === "baseline") baseline = f.baselineSession(false, true);
      polls = 0;
      job = "analyze";
      return json({ recording_id: "r1", job_id: "j1", duration_ms: 1000 }, 202);
    }
    const route = routes[`${req.method} ${path}`];
    const reply = route ? route(null) : json({ code: "not_mocked", message: `${req.method} ${path}` }, 404);
    return reply instanceof Response ? reply : json(reply);
  };

  // A synthetic voice: a tone whose loudness swells like speech, so the real recorder runs.
  navigator.mediaDevices.getUserMedia = async () => {
    const ctx = new AudioContext();
    const voice = ctx.createOscillator();
    const gain = ctx.createGain();
    const swell = ctx.createOscillator();
    const depth = ctx.createGain();
    voice.frequency.value = 180;
    gain.gain.value = 0.15;
    swell.frequency.value = 1.7;
    depth.gain.value = 0.14;
    swell.connect(depth).connect(gain.gain);
    const out = ctx.createMediaStreamDestination();
    voice.connect(gain).connect(out);
    voice.start();
    swell.start();
    return out.stream;
  };
}
