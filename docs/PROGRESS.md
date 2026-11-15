# Progress: app first

Spec: `docs/app-first.md`. Each item is ticked with a one-line proof.

## Part A (branch `app/a-fixes`)

- [ ] A1. Live check with stand-in audio (see Blocked)
- [x] A2. Probe from the app. Proof: `test_probe_route_stores_the_probe_and_onboarding_moves_past_readiness` (harness: onboarding `readiness` → POST `/api/readiness/probe` → `calibration`) passes.
- [x] A3. Audio playback. Proof: `tests/api/test_playback_api.py` (GET recording, POST `/api/model-voice`, GET `/api/model-voice/{clip_id}` with the synthesizer patched to raise) 3 passed.
- [x] A4. One command to start. Proof: with `NOSOLEAR_DATA_DIR=data/verify`, `curl -s 127.0.0.1:8000/` is byte-identical to `apps/web/dist/index.html`; `/setup` 200, `/docs` and `/api/nope` 404; `test_guards.py` 52 passed with `dist` present.
- [x] A5. Three bugs, one regression test each. Proof: `test_seed_is_sent_as_a_string`, `test_get_after_an_all_clean_post_returns_the_result_not_404`, `test_a_double_post_asks_the_coach_once_per_fix` pass.

## Part B (branch `app/b-web`)

- [x] B0. Recorder (`shared/audio`). Proof: `wav.test.ts` checks the header and pins the SHA-256 of the encoded synthetic samples; `test_web_encoder_bytes_are_accepted_by_the_upload_route` builds the same bytes, matches the digest and gets 202 from the upload route.
- [x] B1. Setup. Proof: `useSetup.test.tsx` (missing `.env` lines, Run check moves onboarding past readiness) passes; seen in the browser pane at `/setup` on `data/verify`.
- [x] B2. Calibration. Proof: `useCalibration.test.tsx` (start, resume at the first unrecorded take, n of N, finish job, result) passes.
- [x] B3. Baseline. Proof: `useBaseline.test.tsx` (start, complete, report with clips, provisional flag and skill score) passes.
- [x] B4. Daily session. Proof: `useDaily.test.tsx` (plan, start, upload, analyze job, one feedback POST, fix/not scored/clean cards with a template fallback, complete) passes.
- [x] B5. Home. Proof: `useHomeTarget.test.tsx` passes; in the browser pane `/` went to `/setup`. Nav: Home, Setup, Calibration, Baseline, Today, Progress. `pnpm typecheck`, `pnpm lint` and `pnpm build` pass.

## Part C

- [x] C. HANDOFF "Next", ARCHITECTURE §13 "Later phases" and the done rule. Proof: `git diff --stat` shows 14 lines in HANDOFF and 15 in ARCHITECTURE.

## Decisions

- A1 is Blocked rather than partly run: the spec says so when `doctor` shows a missing key.
- A2 returns each probe's outcome (adapter, ok, safe message); the client re-reads `/api/readiness` and `/api/onboarding` after it.
- A3 model voice is `POST /api/model-voice` `{source: feedback_item|content_item, id, rate_percent}` → `{clip_id, duration_ms}`; the clip id is the cache hash, and the GET checks it is 64 hex characters.
- A4 serves `dist` as the router's default for HTTP only (not a mount), with an `index.html` fallback except under `api/`, `docs/` and `redoc/`. When `dist` is served, the guard also accepts the API's own loopback origin (`create_app`, not `guards.py` or `network_policy.py`).
- A5 all-clean GET: an analyzed daily session with no fix returns its computed report without a POST (nothing would be stored either way). Double POST: a per-session lock, and an `invalid_output` template is no longer re-asked on every POST.
- Part A gate review (one opus subagent, the four kinds only): no key leakage, weakened guards, unmetered paid calls or data loss. PR #51 merged with every check green.
- B: calibration and baseline items now carry `item_id` (additive) so the model voice can name the content item.
- B: the daily screen POSTs feedback once when the analyze job is done; the API lock stops a second coach call.
- B: a calibration take records for up to 10 s; a baseline item for its `max_seconds` (60 s when none).
- B0 follow-up: the recorder now opens its AudioContext at 48 kHz and uploads a 48 kHz WAV; the server's filtered `resample_to_16k` makes the 16 kHz copy, and the browser's linear `resample()` (no low-pass, so it aliased) is gone. The longest item (90 s) is about 8.6 MB, under the unchanged 10 MB cap. Proof: `wav.test.ts` and `test_web_encoder_bytes_are_accepted_by_the_upload_route` pin the new digest; the upload returns 202 with `duration_ms` 1000.

## Blocked

- A1: needs keys in .env. `uv run nosolear doctor` shows `Anthropic  missing  key not set` (Azure Speech is set), so the live run was not started.
