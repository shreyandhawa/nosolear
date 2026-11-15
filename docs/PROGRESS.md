# Progress: app first

Spec: `docs/app-first.md`. Each item is ticked with a one-line proof.

## Part A (branch `app/a-fixes`)

- [ ] A1. Live check with stand-in audio (see Blocked)
- [x] A2. Probe from the app. Proof: `test_probe_route_stores_the_probe_and_onboarding_moves_past_readiness` (harness: onboarding `readiness` → POST `/api/readiness/probe` → `calibration`) passes.
- [x] A3. Audio playback. Proof: `tests/api/test_playback_api.py` (GET recording, POST `/api/model-voice`, GET `/api/model-voice/{clip_id}` with the synthesizer patched to raise) 3 passed.
- [x] A4. One command to start. Proof: with `NOSOLEAR_DATA_DIR=data/verify`, `curl -s 127.0.0.1:8000/` is byte-identical to `apps/web/dist/index.html`; `/setup` 200, `/docs` and `/api/nope` 404; `test_guards.py` 52 passed with `dist` present.
- [x] A5. Three bugs, one regression test each. Proof: `test_seed_is_sent_as_a_string`, `test_get_after_an_all_clean_post_returns_the_result_not_404`, `test_a_double_post_asks_the_coach_once_per_fix` pass.

## Part B (branch `app/b-web`)

- [ ] B0. Recorder
- [ ] B1. Setup
- [ ] B2. Calibration
- [ ] B3. Baseline
- [ ] B4. Daily session
- [ ] B5. Home

## Part C

- [ ] C. HANDOFF "Next", ARCHITECTURE §13 "Later phases" and the done rule

## Decisions

- A1 is Blocked rather than partly run: the spec says so when `doctor` shows a missing key.
- A2 returns each probe's outcome (adapter, ok, safe message); the client re-reads `/api/readiness` and `/api/onboarding` after it.
- A3 model voice is `POST /api/model-voice` `{source: feedback_item|content_item, id, rate_percent}` → `{clip_id, duration_ms}`; the clip id is the cache hash, and the GET checks it is 64 hex characters.
- A4 serves `dist` as the router's default for HTTP only (not a mount), with an `index.html` fallback except under `api/`, `docs/` and `redoc/`. When `dist` is served, the guard also accepts the API's own loopback origin (`create_app`, not `guards.py` or `network_policy.py`).
- A5 all-clean GET: an analyzed daily session with no fix returns its computed report without a POST (nothing would be stored either way). Double POST: a per-session lock, and an `invalid_output` template is no longer re-asked on every POST.

## Blocked

- A1: needs keys in .env. `uv run nosolear doctor` shows `Anthropic  missing  key not set` (Azure Speech is set), so the live run was not started.
