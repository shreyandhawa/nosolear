// The API responses the hook tests mock. The dev-only mock (`src/dev/mock.ts`) serves the same
// data so every screen state can be seen without provider keys. Never imported by app code.

export const onboarding = (step: string) => ({
  step,
  blockers: [],
  calibration: "not_run",
  baseline: "not_started",
  baseline_session_id: null,
});

const row = (component: string, status: string, fix: string | null, reason = "test") => ({
  component,
  label: component,
  status,
  reason,
  fix,
});

export const readiness = (probed: boolean) => ({
  ready: probed,
  rows: [
    row("azure_speech", "ready", null),
    row("anthropic", "missing", "set NOSOLEAR_ANTHROPIC_API_KEY in .env"),
    row("azure_capabilities", probed ? "ready" : "not_probed", "run the check"),
  ],
});

export const probeRun = { outcomes: [{ adapter: "azure_pa", ok: true, message: "nbest_phonemes True" }] };

const calibrationItem = (order: number, recorded: boolean) => ({
  attempt_id: `a${order}`,
  item_id: `w${order}`,
  order,
  error_key: "sound.sub.v.w",
  word: "very",
  deliberate: order === 2,
  take: 1,
  instruction: "Say it as you usually would.",
  stand_in_text: "very",
  recorded,
  job_status: recorded ? "done" : null,
});

export const calibrationRun = (status: string, recorded: boolean[]) => ({
  run_id: "r1",
  session_id: "s1",
  status,
  scoring_config_id: null,
  started_at: "2026-11-15T10:00:00Z",
  completed_at: null,
  items: recorded.map((r, n) => calibrationItem(n + 1, r)),
  results:
    status === "done"
      ? [
          {
            detector: "azure_pa",
            error_key: "sound.sub.v.w",
            errors: 1,
            hits: 1,
            controls: 1,
            false_alarms: 0,
            correct_takes: 1,
            correct_flags: 0,
            covered: true,
            enabled: true,
            hit_rate: 1,
            false_alarm_rate: 0,
            correct_take_flag_rate: 0,
            warning: null,
          },
        ]
      : [],
});

export const calibrateJob = {
  id: "j1",
  kind: "calibrate",
  attempt_id: null,
  status: "done",
  progress: 1,
  step: null,
  steps: [],
  tries: 1,
};

export const baselineSession = (completed: boolean, recorded = true) => ({
  session_id: "b1",
  protocol_version: 1,
  started_at: "2026-11-15T10:00:00Z",
  completed_at: completed ? "2026-11-15T10:20:00Z" : null,
  items: [
    {
      attempt_id: "a1",
      item_id: "p1",
      order: 1,
      section: "Read aloud",
      step: "read",
      text: "A very good day.",
      scripted: true,
      max_seconds: 30,
      start_limit_seconds: null,
      stand_in_text: "A very good day.",
      recorded,
      job_status: recorded ? "done" : null,
    },
  ],
});

export const baselineReport = {
  session_id: "b1",
  completed_at: "2026-11-15T10:20:00Z",
  calibration: "done",
  scoring_config_id: "c1",
  snapshot_id: "x1",
  notes: [],
  skill_scores: [{ skill: "sounds", score: 72, scores: {}, values: {} }],
  items: [
    {
      error_key: "sound.sub.v.w",
      description: "/v/ said as /w/",
      skill: "sounds",
      impact: 3,
      status: "active",
      p_hat: 0.3,
      ci_low: 0.1,
      ci_high: 0.5,
      n_eff: 4,
      priority: 0.9,
      provisional: true,
      clips: [{ attempt_id: "a1", start_ms: 100, end_ms: 400, word: "very", expected: "v", produced: "w" }],
    },
  ],
};

export const plan = {
  id: "p1",
  for_date: "2026-11-15",
  seed: "18446744073709551615",
  protocol_version: 1,
  foci: [
    { skill: "sounds", error_key: "sound.sub.θ.t", description: "T instead of TH", impact: 3, p_hat: 0.3, provisional: true, source: "profile", status: "active" },
    { skill: "on_the_spot", error_key: "fluency.filler", description: "Filler words", impact: 2, p_hat: 0.2, provisional: false, source: "profile", status: "unknown" },
    { skill: "articulate", error_key: "clarity.vague", description: "Vague wording", impact: 2, p_hat: 0.25, provisional: false, source: "fallback", status: "unknown" },
  ],
  probe: null,
  prompt: { id: "q1", text: "Describe your morning.", target_keys: [] },
  drills: [],
  steps: [
    { kind: "speak", skill: null, duration_s: 60 },
    { kind: "analyze", skill: null, duration_s: 60 },
    { kind: "feedback", skill: null, duration_s: 180 },
    { kind: "drill", skill: "sounds", duration_s: 300 },
    { kind: "log", skill: null, duration_s: 60 },
  ],
};

export const dailySession = {
  session_id: "s1",
  plan_id: "p1",
  attempts: [{ id: "a1", step: "speak", prompt_text: "Describe your morning." }],
  job_id: null,
  completed: false,
};

export const analyzeJob = (status = "done", progress = 1) => ({
  id: "j1",
  kind: "analyze",
  attempt_id: "a1",
  status,
  progress,
  step: null,
  steps: [{ name: "score", state: status === "done" ? "done" : "running", error_code: null, message: null }],
  tries: 1,
});

export const feedback = {
  session_id: "s1",
  degraded: true,
  skills: [
    {
      skill: "sounds",
      state: "fix",
      item: {
        id: "f1",
        error_key: "sound.sub.v.w",
        message: "Teeth on lip.",
        model_text: "very",
        source: "template",
        fallback_reason: "cap_exceeded",
        attempt_id: "a1",
        start_ms: 100,
        end_ms: 300,
        word: "very",
      },
    },
    { skill: "on_the_spot", state: "not_scored", item: null },
    { skill: "articulate", state: "clean", item: null },
  ],
};

export const completed = { session_id: "s1", completed_at: "2026-11-15T10:10:00Z", already_completed: false };

export const profile = {
  as_of: "2026-11-10T12:00:00Z",
  taxonomy_version: 1,
  algo_version: 1,
  entries: [
    {
      error_key: "sound.sub.v.w",
      description: "/v/ said as /w/",
      family: "sound",
      skill: "sounds",
      impact: 3,
      status: "active",
      p_hat: 0.25,
      ci_low: 0.17,
      ci_high: 0.34,
      n_eff: 31.6,
      priority: 0.75,
      last_seen_at: "2026-11-10T12:00:00Z",
      provisional: false,
    },
    {
      error_key: "sound.sub.th.t",
      description: "/θ/ said as /t/",
      family: "sound",
      skill: "sounds",
      impact: 2,
      status: "unknown",
      p_hat: 0.1,
      ci_low: 0.04,
      ci_high: 0.2,
      n_eff: 3.2,
      priority: 0.2,
      last_seen_at: "2026-11-09T12:00:00Z",
      provisional: false,
    },
  ],
};
