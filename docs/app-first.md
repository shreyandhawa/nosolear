# App first: fixes and the working web app

Repo: Nosolear, `main` at 70d04e8. Work through every item below without stopping to ask or report. This file is the whole spec; commit it with Part A.

## Direction (overrides HANDOFF and ARCHITECTURE where they differ)

- The owner records nothing until the app is complete. Calibration and the baseline are the app's first run, done in the browser. Verify everything with stand-in audio (Azure TTS), never his voice.
- Everything a user does happens in the web app. The CLI stays for debugging. A feature reachable only from the CLI or API is not done.
- Laptop first (1280 px and wider). Phone and token mode stay last.
- Visual design is a later pass. Here the web app is plain: semantic HTML, existing Tailwind utilities for basic layout, logic in hooks, presentational components.

## How to work: fast and cheap

- Do not read `docs/superpowers/HANDOFF.md`, `docs/ARCHITECTURE.md` or the old plans in full. Use the pointers below and `grep` when one is not enough.
- Ponytail at `full`: the smallest diff that works. Reuse what exists. No new ports, wrappers, settings, abstractions, documents or CI jobs.
- No brainstorming, no plan documents, no new documents other than `docs/PROGRESS.md`, no subagents (except the one review in the gate), no narration between steps. Decide, note the decision in one line in `docs/PROGRESS.md`, and keep going.
- Write tests only where an item's proof names one. No other tests.
- Keep output small: `-q` flags, long output through `tail -n 30`. While working, run only the tests for the files you touched. Run the full suite only at the gate.
- Read independent files in parallel.
- Do not wait on CI. Open the Part A pull request, keep working on Part B locally on `app/b-web` (branched from `app/a-fixes`), and run `gh pr checks --watch` only when you are ready to merge. This repo squash-merges, so do not open Part B as a stacked pull request: after Part A merges, run `git rebase --onto main app/a-fixes app/b-web`, then open Part B against `main`.
- After each item, tick it in `docs/PROGRESS.md` with a one-line proof and commit. If context is compacted, re-read this file and `docs/PROGRESS.md` and continue.
- Stuck on an item after two different attempts: log it under "Blocked" in `docs/PROGRESS.md` with the reason and move on.

## Never

- Never read or print `.env`. Check for keys with `uv run nosolear doctor`.
- Never run stand-in or live checks against the default data dir. Use `NOSOLEAR_DATA_DIR=$PWD/data/verify`, so the owner's real first run starts clean.
- Never weaken the loopback and origin guards, log scrubbing, metering or caps. Never raise a cap.
- Never let a GET trigger a paid call.
- Never add a dependency. None is needed.
- Never commit an audio file or anything under a `data/` path. The hygiene check refuses both, so build test audio in code.
- Never delete data or branches, force-push, or bypass a required check. No migration is expected; if one is unavoidable it is additive only.
- Never style the app.

## Pointers

Running things: the CLI runs as `cd apps/api && uv run nosolear ...`. Settings read `.env` from the repo root. The server migrates the database when it starts. CLI commands other than `doctor` talk to a running server, so the server and the CLI need the same `NOSOLEAR_DATA_DIR`.

API (`apps/api/src/nosolear/`):
- App and routers: `api/app.py` `create_app` (routers about line 150, guard middleware about line 175). Guards: `api/guards.py`, `domain/network_policy.py`.
- Composition: `api/deps.py` (`build_services`, `build_providers`, `build_stand_in_synthesizer`).
- Probe: `app/probe_capabilities.py`. Onboarding blocks on it in `domain/onboarding.py` (`BLOCKING`). Readiness route: `api/readiness_routes.py`.
- Recording upload: `api/recording_routes.py` (`POST /api/attempts/{attempt_id}/recording`, raw `audio/wav`, 10 MB cap). Stored audio: `ports/audio.py` (`RecordingStore.for_attempt`, `AudioStore.resolve`).
- Model voice: cached, metered synthesizer in `adapters/tts_cache.py` (`synthesize(text, rate_percent=0)`).
- Plan seed: `api/schemas.py` `PlanOut.seed`, `api/plan_routes.py`. Feedback: `api/feedback_routes.py` (the 404 `feedback_not_generated`), `app/generate_feedback.py`.
- Stand-in audio: `first_run_cli.py` (`_stand_in`). Test harness: `tests/harness.py`. Live tests: `tests/live/`.
- Every new GET goes in `READ_ONLY_GET_ROUTES` in `tests/api/test_guards.py`.

Routes that already exist: `GET /api/onboarding` (step is `readiness`, `calibration`, `baseline`, `report` or `daily_plan`), `GET /api/readiness`, `POST|GET /api/calibration`, `/api/calibration/skip`, `/api/calibration/finish`, `POST|GET /api/baseline`, `/api/baseline/complete`, `/api/baseline/report`, `POST|GET /api/plan/today`, `POST /api/plan/today/session`, `GET /api/jobs/{id}`, `POST|GET /api/sessions/{id}/feedback`, `POST /api/sessions/{id}/complete`, `GET /api/profile`.

Web (`apps/web/src/`): router in `app/router.tsx`, typed client in `shared/api/client.ts`. Copy the pattern in `features/progress/` (`useProfile.ts`, `ProfilePage.tsx`). Features never import each other. Run `make gen-api` after any API change.

## Part A: fixes (branch `app/a-fixes`, one pull request)

- **A1. Live check with stand-in audio.** If `doctor` shows keys are missing, log this item as Blocked ("needs keys in .env") and continue. Otherwise start `nosolear serve` in the background with the scratch data dir and, with the same variable set, run: `nosolear doctor --probe`, `make test-live`, `nosolear calibrate start`, `nosolear stand-in calibration`, `nosolear calibrate finish`, `nosolear baseline start`, `nosolear stand-in baseline`, `nosolear baseline complete`, and `nosolear daily run WAV` using a cached TTS clip from the scratch data dir as the WAV. Stop the server afterwards. Spend is approved within the existing caps. Fix what breaks in adapters and parsers. *Proof: tail of each command.*
- **A2. Probe from the app.** `POST /api/readiness/probe` runs the existing `probe_capabilities`. *Proof: one route test; in the harness, onboarding moves past `readiness` after it.*
- **A3. Audio playback.** `GET /api/attempts/{attempt_id}/recording` serves the stored WAV (the client seeks to `start_ms` and `end_ms`). For the model voice: a POST that takes the id of stored text (a feedback item or content item, never free text) and a rate, synthesizes through the cached metered synthesizer, and returns a clip id; a GET serves a cached clip only. *Proof: one test per route, plus one showing the GET never calls the synthesizer.*
- **A4. One command to start.** `nosolear serve` serves `apps/web/dist` from the same origin when it exists. Add `make app` (build, then serve) and name it in the README's Run section. Across Part A, correct only the README lines a change makes false (for example, that the probe runs only from the CLI). *Proof: `curl -s 127.0.0.1:8000/` returns the built `index.html`; guard tests pass.*
- **A5. Three bugs, one regression test each.** Send `PlanOut.seed` as a string. A feedback GET after an all-clean session returns the stored result, not 404. A double feedback POST does not call the coach twice.

## Part B: the working web app (branch `app/b-web`, one pull request)

- **B0. Recorder** in `shared/audio`: `getUserMedia`, an AudioWorklet, a 16 kHz mono 16-bit WAV. Click or Space toggles. Expose a live level value, auto-stop at the item's limit, handle permission denied, keep the recording in memory until the upload succeeds, and offer retry. *Proof: a test that the encoder's output from synthetic samples has a valid header, and that the same bytes are accepted by the running upload route.*
- **B1. Setup:** readiness rows with status, reason and fix, the `.env` lines still missing, and a "Run check" button (A2).
- **B2. Calibration:** start or skip; one take per screen (word, what to say, model voice, record, advance); n of N; resume; finish with the job's progress and the result.
- **B3. Baseline:** items in order with their limits; complete; the report (ranked errors, clips, provisional flags, a score per skill).
- **B4. Daily session:** plan, start, prompt, 60-second recording, the analyze job's real steps, one feedback card per skill with the user's clip beside the model voice, complete. Show "not scored today" and the template fallback when the API reports them.
- **B5. Home:** `/` goes to the step `GET /api/onboarding` names. Navigation lists only screens that exist. The profile page stays as Progress.

State: TanStack Query plus a plain reducer. *Proof for B1 to B5: one happy-path test per screen's hook or reducer against mocked API responses; `pnpm typecheck`, `pnpm lint` and `pnpm build` pass.*

## Part C: write down the new order (three small edits, in the Part B pull request)

- Replace the "Next" list in HANDOFF with at most twelve lines pointing here.
- Replace the bullets under "Later phases" in ARCHITECTURE section 13 with: 1 design pass on these screens; 2 drills, one family at a time, each as backend, API and screen together, sounds first; 3 progress screens; 4 live voice conversation, spike first; 5 token mode and phone access; 6 in-app key entry, write-only.
- Add one line there: a feature is done when the owner can use it in the browser, verified with stand-in audio.

## Gate before each merge (only these)

1. `make test` and `make lint` exit 0.
2. `git diff main --stat` shows no change to `domain/network_policy.py` or the scrubbing code, and `api/guards.py` changed only if A4 needed it.
3. The new paid paths (A2, A3) go through the existing metered ports, and no GET reaches them.
4. Part A only: one review of the diff in a fresh context (`/code-review` or a single subagent), told to report only key leakage, weakened guards, unmetered paid calls and data loss. Fix those. Ignore everything else.
5. Required checks are green. Then merge.

## Finish

Print `docs/PROGRESS.md`, the last line of `make test` and of `make lint` on `main`, and `gh pr list --state merged --limit 2`. Then say in five lines or fewer what the owner can now do in the browser, what was verified only by test and not in a real browser, and anything Blocked.
