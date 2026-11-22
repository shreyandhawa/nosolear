# Progress: app first

Spec: `docs/app-first.md`. Each item is ticked with a one-line proof.

## Part A (branch `app/a-fixes`)

- [x] A1. Live check with stand-in audio. Proof: `make smoke` on 2026-11-22 ran `doctor --probe` (`azure_pa` ok), calibration, baseline, the report and `stand-in daily` against the real API with no Anthropic key; every job ended `done`. Details under "End-to-end run" below.
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

## End-to-end run (2026-11-22)

After PRs #66 (first-run bugs), #67 (Baseline and Report pages) and #68 (Welcome and Setup), with the owner's first-run `data/` moved to `~/Nosolear-backups/data-2026-11-22/` and no Anthropic key.

How: `make smoke` (stand-in TTS audio through the real API on a temporary data dir), then `make app` on a copy of that data dir and every page walked in the browser pane at 1280×800, then a fresh `data/` for Today: build the plan, upload the owner's first-run daily take (29.6 s) with `nosolear upload --attempt-id`, leave the page and come back. The whole run spent about 2.5 minutes of Azure audio (the usage pill read 0.034 h after the smoke run).

Proof:
- `doctor --probe`: `ok azure_pa: nbest_phonemes True, prosody True`; `doctor` without the coach key prints `Anthropic missing` and exits 0.
- Smoke DB: 175 recordings for 175 attempts (one each); 110 distinct audio hashes, because stand-in takes with the same text are the same cached TTS clip. Jobs: analyze 175 done, calibrate 1 done (its `controls` step passed, so `ɛɹ` maps), rescore 1 done. No `internal_error` and no unmapped-symbol failure in the jobs or the server log.
- Today: after leaving and coming back while the job ran, the page showed "Analyzing" with the live steps (score done, transcribe running), then the feedback. The completed smoke session reopened as done with its stored feedback. Fresh DB: 1 recording, 1 attempt, 1 job done; no server errors.

Found and fixed in PR 4, each with a test:
- Every first-run CLI command except `upload` crashed with `AttributeError: 'Namespace' object has no attribute 'base_url'` when run from a shell; the tests always injected a client (since #35). `test_first_run_commands_build_their_own_client_from_the_settings`.
- Azure answered a valid key with `AuthenticationFailure`/`Forbidden` on 16 of 175 takes; all 16 passed when resumed. Those codes are now retried; a wrong key still ends with the key message. `test_classify`.
- Calibration's result was a 19-row table of raw keys (`sound.sub.f.p`, each twice with no detector), overflowing its slot. It now lists the detectors that stay off, as phones with their detector, and folds the full table away. `CalibrationPage.test.tsx`.
- The Report always printed "Calibration is calibrated, so provisional flags may change": it compared with `"done"`, but the state is `"calibrated"`, and the API's notes already cover calibration. It also showed an empty "Your clips" label for a prosody error. `pages.test.tsx`.
- The no-coach report note said the coach "was unavailable"; it now says what was not scored without it.
- With real readiness rows, Setup's Notes slot overflowed; all-ready local parts now fold into one line. `SetupPage.test.tsx`.
- Today's feedback card, for a prosody fix, showed the raw key `prosody.monotone` as its title, empty "Your word" rows, and "the coach could not be reached" when no key is set.
- `stand-in daily` read the prompt's question aloud; it now answers with a fixed passage.
- `make smoke` collided with another local server on a fixed port; it now asks the OS for a free one.

Not covered: real-voice calibration and baseline (stand-in TTS is clean speech, so the report has one error), the coach (no key), and other viewport sizes.
