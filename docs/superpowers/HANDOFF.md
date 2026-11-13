# Handoff

Read this first in a new session, then continue from **Next**.

## Current phase

Phase 0b (open-source foundation) is done as of 2026-11-13. Next is Phase 0c (audio, jobs, ledger). Gate 2 passed earlier, when the phase plans PR #13 merged as 391b639.

## Done

- 2026-11-12: Surveyed the docs, `apps/api`, CI, tooling and `p0b/spikes`. Baseline on `main` was green (191 API tests and 10 web tests; lint clean).
- 2026-11-12: Brainstormed the design with the owner. All sections were approved.
- 2026-11-12: [PR #12](https://github.com/shreyandhawa/nosolear/pull/12) merged as 19097e7: the revised `docs/ARCHITECTURE.md`, independently reviewed for security and consistency.
- 2026-11-12: Wrote the five phase plans, reconciled across plans; merged as [PR #13](https://github.com/shreyandhawa/nosolear/pull/13), 391b639 (Gate 2).
- 2026-11-12: Turned on GitHub private vulnerability reporting for the repo. `gh api repos/shreyandhawa/nosolear/private-vulnerability-reporting -q .enabled` prints `true`.
- 2026-11-12: Phase 0b Task 1: `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `PRIVACY.md` and their test.
- 2026-11-12: Phase 0b Task 2: `THIRD_PARTY_NOTICES`, `scripts/third_party_licences.py` (`--check` for drift) and `test_notices.py`. Licences verified against upstream on 2026-11-12.
- 2026-11-12: Phase 0b Task 3: the full `Settings` tree (loopback-only host and origins, key-length and pattern checks, timezone, caps), `.env.example` and the CLI error path; tests never load the real `.env`.
- 2026-11-12: Phase 0b Task 4: `scrub` (domain), log-record-factory secret scrubbing, private data dir (0700/0600, symlinks skipped, foreign owner refused) and `prepare_process` wired into the CLI and the app lifespan.
- 2026-11-12: Phase 0b Task 5: language packs (`domain/packs.py`, `calibration_items.py`, `adapters/content_files.py`, `content/packs/{neutral,nepali}`, `content/calibration/items.toml`) with the Phase 0a hypothesis keys moved into the `nepali` pack.
- 2026-11-12: Phase 0b Task 6: the active pack drives profile priors (`build_profile(..., pack=)`, `Profile.pack_id`, migration `0003_pack_id`, `ensure_profile_pack` on startup, `pack error:` exit 2 in the CLI); the taxonomy `hypothesis` flag is gone.
- 2026-11-12: Phase 0b Task 7: readiness (`domain/readiness.py`, `check_readiness`, `SystemEnvironment`, `GET /api/readiness`, `nosolear doctor`; `doctor --probe` waits for Phase 0d). Keys enter only as booleans.
- 2026-11-12: Phase 0b Task 8: network guards (`domain/network_policy.py`, outermost `RequestGuardMiddleware`: loopback peer, exact Host/Origin membership, no cross-site fetch), CORS limited to the app origins, `nosolear serve` (`proxy_headers=False`), Makefile uses it; API tests use `loopback_client`.
- 2026-11-12: Phase 0b Task 9: CI `audit` job (pip-audit 2.10.1 on the exported lockfile, pnpm audit), `api` matrix on ubuntu and macOS behind a stable `api` gate job, pytest `live` marker (excluded by default), `make test-live`, and the `live_settings` and `require_keys` helpers. With the owner's approval, main's required checks are exactly `hygiene`, `api`, `web`, `contract` and `audit`; nothing else in branch protection changed.
- 2026-11-12: Phase 0b Task 10: the README is now the setup guide (platforms, prerequisites, keys, set up, `nosolear doctor`, run, extras, what leaves your machine, costs, security), checked by `tests/docs/test_readme.py` against the Makefile, the CLI parser and the settings.
- 2026-11-12: Phase 0b Task 11: the planted-fake-key harness (`tests/security/planted.py`, `test_no_key_leaks.py`): one parametrised test over `LEAK_SURFACES` (settings dumps, log messages, tracebacks and uvicorn's formatter, API responses, OpenAPI, `doctor`, validation errors, repo files), plus a stable sentinel-based Hypothesis property in `test_check_readiness.py`. Later phases append `@leak_surface` producers for their adapter error paths, job `steps_json`, ledger rows and logs: define producers in `tests/security/planted.py` or a `tests/security/surfaces_*.py` module (anywhere else registers too late). The log record factory now clears `record.exc_info` after caching the scrubbed `exc_text`.
- 2026-11-13: Phase 0b Task 12, phase verification:
  - Whole-phase checks on a fresh clone of `main` (0b114c5): `make setup`, `make test` (728 API, 10 web), `make lint`, `make gen-api` (no diff) and the heavy Hypothesis profile (214) all pass. `make test-live` without keys passes (1 test); no live adapters exist yet.
  - The §13 walk, with planted fake keys in a temp `.env`, passed. `doctor` lists what is configured and what is missing and leaks no key, fragment, base64 form or length. `NOSOLEAR_HOST=0.0.0.0 nosolear serve` exits 2. With `make api` running, `Host: evil.com`, `Origin: https://evil.example`, `Origin: null` and `Sec-Fetch-Site: cross-site` each get 403. Plain `uvicorn --host 0.0.0.0` answers a request from the machine's LAN interface address with 403; no second machine was used.
  - [PR #27](https://github.com/shreyandhawa/nosolear/pull/27): `ARCHITECTURE.md` §17 and the README licence line now say CrisperWhisper's code is MIT and its weights are CC BY-NC 4.0, and that `mlx-community/whisper-large-v3-turbo` declares no licence. The answered §18 question is gone.
  - The phase security review ran as an opus subagent over `391b639..main`, using the `/security-review` method. It found 0 High, 0 Medium and 3 Low. [PR #28](https://github.com/shreyandhawa/nosolear/pull/28) fixes all three:
    - The Vite proxy keeps the browser's Host header, so the API's DNS-rebinding check applies to proxied requests.
    - The Vite dev and preview servers are pinned to `localhost` with `strictPort`, and a config plugin refuses any non-loopback `--host`.
    - pnpm audit fails at moderate, with explicit GHSA waivers; the CI workflow also runs weekly.
    - pip-audit also runs on macOS, behind the stable `audit` gate.
  - PR #28 also adds hardening: CI `permissions: contents: read`, the hygiene check refuses `.env`, `/docs` and `/redoc` are off (they loaded JavaScript from a CDN), and the doctor usage row states the right cap periods.
  - The final whole-phase review (opus) found 0 Critical and 3 Important. [PR #29](https://github.com/shreyandhawa/nosolear/pull/29) fixes:
    - The README's Node/pnpm route: Node 26 has no Corepack, so the README installs `pnpm@12.16.1` and adds the fnm shell hook; `make setup` turns on the git hooks first.
    - `~` in `NOSOLEAR_DATA_DIR` now expands to the home directory.
    - Two vacuous security tests (the leak harness's negative control and the `stack_info` scrub).
    - `HF_HUB_DISABLE_TELEMETRY` is now always `1`.
    - SECURITY.md marks the unbuilt mitigations as planned.
    - A pack-change rebuild is logged.
    - The §14 example matches the code.
    - Three CI-shape test gaps.
- 2026-11-13: Phase 0c Task 1: pure WAV parsing, validation and resampling (`domain/audio.py`: `parse_wav`, `check_declared_length`, `to_16k`, `encode_wav`) and the typed errors (`domain/errors.py`), with `numpy==2.5.4` pinned as a direct dependency and the synthetic WAV builders in `tests/wavs.py`.
- 2026-11-13: Phase 0c Task 2: the `AudioStore` port, `FilesystemAudioStore` (temp file in `recordings/.incoming/`, validate and resample to 16 kHz, `recordings/<uuid>.wav` at 0600, symlink-safe `resolve`) and `FakeAudioStore` in `tests/fakes.py`, with a shared contract test.
- 2026-11-13: Phase 0c Task 3: migration `0004_recordings_jobs_ledger` and models for `recordings`, `jobs`, `usage_ledger` and `analyses` (CHECKs, partial unique indexes on analyses), plus `PRAGMA busy_timeout=5000`.
- 2026-11-13: Phase 0c Task 4: the usage ledger (`domain/budget.py` caps, UTC periods and `fits`; `ports/ledger.py`; `persistence/ledger.py` `SqliteUsageLedger` reserving under `BEGIN IMMEDIATE`, with orphan reservations settled at their estimate on startup; `FakeUsageLedger` in `tests/fakes.py`).
- 2026-11-13: Phase 0c Task 5: the metered layer (`budget/meter.py`: `Meter.call` reserves before the call, releases on `RequestNotSent`, records the estimate on any other failure; `metered_method`), the composition order (`budget/compose.py`: `compose_paid_port` gives cache -> retry -> metered -> raw, `layers_of` checks it), `build_paid_ports` (empty until Phase 0d), and the SDK-import scanner in `tests/budget`.
- 2026-11-13: Phase 0c Task 6: the job domain (`domain/jobs.py`: plans, step states, `resume_plan`, `recover_running`), the `JobQueue` port, and `SqliteJobQueue` (`persistence/job_queue.py`, claims under `BEGIN IMMEDIATE` through the shared `persistence/transactions.py`, FIFO by `created_at` then rowid) with `FakeJobQueue` in `tests/fakes.py`.

## In progress

- Nothing open. Phase 0b is merged (PRs #14–#29).
- The Phase 0b subagent-driven-development workspace was deleted at the close of the phase. Git history and this file are the record.

## Next

1. Plan and execute Phase 0c: `docs/superpowers/plans/2026-11-12-phase-0c-audio-jobs-ledger.md`, branch prefix `p0c/`.
   - Use `superpowers:subagent-driven-development`. It creates a fresh ledger under `.superpowers/sdd/`.
   - One branch and one PR per task, with a fresh implementer subagent and a different reviewer subagent each time. Squash-merge on green CI with `--subject`.
   - Pick up the Phase 0c items under "Carried to later phases" below.
2. Any task that adds a dependency reruns `uv run --project apps/api python scripts/third_party_licences.py`.
3. At the end of each phase:
   - Run the security review over the phase range as an opus subagent with the `/security-review` method. The stock `/security-review` only diffs the current branch against `origin/HEAD`, which is empty on `main`.
   - Update this file and hand off to a fresh session.

## What Phase 0c and later can rely on

- **Settings.** The `Settings` tree, including:
  - `timezone` and `Settings.tzinfo`, `job_workers`, `faster_whisper_model` and `mlx_whisper_model`.
  - `data_dir`, with `~` expanded.
  - `LOOPBACK_NAMES`, `CONTENT_DIR`, `MIN_KEY_LENGTH`, `Settings.secret_values()`, `Settings.packs_dir` and `settings_error_summary(exc)`.

  A later phase that needs a new setting adds it to this tree and to `.env.example` in its own task.
- **Scrubbing and startup.** `domain/redaction.scrub`, `logging_setup.install_secret_scrubbing`, and `startup.prepare_process(settings, *, create_data_dir)`. `prepare_process` sets umask 077 and forces `HF_HUB_DISABLE_TELEMETRY=1`.
- **Private files.** `adapters/private_fs.py`: `ensure_private_dir`, `tighten_tree` and `make_private_file(path)`. 0c's `AudioStore` and 0d's TTS cache use them to write owner-only files.
- **Packs and calibration.**
  - Packs: `LanguagePack`, `PackHypothesis`, `CalibrationExtra`, `parse_pack`, `validate_pack`, `load_pack(packs_dir, pack_id)` and `list_pack_ids`.
  - Calibration: `CalibrationSpec`, `CalibrationItem`, `build_calibration_items` and `load_calibration_specs` in `adapters/content_files.py`.
- **Profiles.**
  - Functions: `build_profile(..., pack)`, `rebuild_profile(..., pack)`, `Profile.pack_id`, `LanguagePack.prior_for(key)`, `ProfilePackReader` and `deps.load_active_pack(settings)`.
  - Columns: `profile_entries.pack_id` and `profile_snapshots.pack_id` (migration `0003`, `down_revision = "0002"`).
- **Readiness.**
  - Types: `Component`, `ReadinessStatus`, `ReadinessRow`, `ReadinessReport` and `ReadinessInputs`. `usage: UsageSnapshot | None` is for 0c to fill. `capabilities: CapabilityFindings | None` is for 0d to replace.
  - Entry points: `build_readiness`, `check_readiness(settings, env)`, `EnvironmentProbe`, `deps.get_readiness_report`, `GET /api/readiness` (`getReadiness`) and `nosolear doctor`.
  - The usage row's wording with usage figures is `Azure 0.4 of 4.5 h and TTS 12k of 450k chars this month, Claude 3k of 100k tokens today`.
- **Network.**
  - `domain/network_policy.check_request`, `RequestGuardMiddleware` and `nosolear serve [--reload]`.
  - Every new `GET /api/...` route must be added to `READ_ONLY_GET_ROUTES` in `tests/api/test_guards.py`. `/docs` and `/redoc` are off and `/openapi.json` stays.
  - Phase 6's token mode relaxes origins only in `Settings.app_origins` validation, and adds its Bearer check in `RequestGuardMiddleware`.
- **Web dev server.** `apps/web/vite-plugins/loopbackOnly.ts` (`nosolear:loopback-only`). The proxy is `changeOrigin: false`, and the dev and preview servers are pinned to `localhost` with `strictPort`.
- **Tests and scripts.**
  - The `live` marker, `make test-live` and `tests/live/conftest.py` (`live_settings`, `require_keys`).
  - `tests/security/planted.py`: `PLANTED_*`, `planted_settings`, `assert_no_planted_key` and `@leak_surface`.
  - `tests/factories.py`: `make_settings`, `loopback_client`, `FakeEnvironment`, `NEPALI`, `NEUTRAL` and `PACK = NEPALI`.
  - `tests/ci/test_workflow_shape.py` and `scripts/third_party_licences.py`.
- **CI.**
  - Check names: `hygiene`, `api` (gate), `api (ubuntu-latest)`, `api (macos-latest)`, `web`, `contract`, `audit` (gate), `audit (ubuntu-latest)` and `audit (macos-latest)`. The required checks are `hygiene`, `api`, `web`, `contract` and `audit`.
  - The workflow also runs every Monday at 06:00 UTC.
  - pnpm advisory waivers go in `apps/web/pnpm-workspace.yaml` under `auditConfig.ignoreGhsas`, with a comment. pip-audit waivers use `--ignore-vuln` with a comment.

## Carried to later phases (from the Phase 0b reviews)

- **Phase 0c:**
  - Move the lifespan's adapter construction (`ObservationRepository`, `ProfileRepository`, `SystemClock`) into `build_services`, and dispose of the engine on any startup error, not only `PackError`.
  - Replace the `assert pack is not None` narrowing in `cli.py` with explicit branches.
  - Add a `ProfileStore` fake.
  - When `AudioStore` writes 0600 recordings, add a data-at-rest bullet to SECURITY.md and turn its "planned (Phase 0c)" upload-checks line into present tense.
- **Phase 0d:**
  - **Key-leak items** (the security review's item C). No Phase 0b code encodes or sends a key, so these start when the adapters do:
    - Let derived credentials (for example Azure `issueToken` JWTs) be registered with the scrubber at runtime.
    - Pin the `httpx`, `httpcore`, Anthropic SDK and Azure Speech SDK loggers at WARNING, and run the leak harness over adapter error paths with their DEBUG logging on.
    - Install a scrubbing `sys.excepthook` in `prepare_process`.
    - Check that no adapter passes a key-bearing `extra=`.
    - Optionally add base64 forms to `secret_forms`.
    - Guard `install_secret_scrubbing` against recursing through a library's factory that chains back to ours.
  - **Licence script.** `scripts/third_party_licences.py` cannot build a complete table on one machine once the `local` and `apple` extras exist. Pick one canonical platform, or add per-platform rows. The web table already has darwin-only rows.
  - Check the licence of the CrisperWhisper revision that 0d pins.
  - **Readiness.**
    - Flag unknown `NOSOLEAR_*` names in `.env`.
    - Report a data dir that is a file or belongs to another user as not ready (today `serve` fails loudly).
    - Unify the `Transcriber` alias with 0d's `TranscriberChoice`.
  - **README.** Add the synthesized-audio traffic of `doctor --probe` and `make test-live` to "what leaves your machine" once they call out.
  - **PRIVACY.md.** Its test checks only the provider names. Once providers send data, make it check each row's content against ARCHITECTURE §16.
- **Phase 0e:**
  - Reject unknown keys in `parse_pack`. A `[[hypothesis]]` typo currently yields an empty pack.
  - Key pack-change rebuilds on a content hash, not only the pack id.
  - Detect duplicate calibration extras, and check extras against the spec words.
- **Phase 2:**
  - The Vite proxy target hard-codes port 8000, so it doesn't follow `NOSOLEAR_PORT`.
  - `vite preview`'s port 4173 is not in the Host allowlist, so preview fails closed.
  - Run `third_party_licences.py --check` in CI once the canonical-platform question is settled.
- **Phase 6:** align the host validator, which accepts `127.0.0.0/8` and is case-sensitive, with the origin validator's `LOOPBACK_NAMES` when token mode revisits both.
- **CI hardening, whenever convenient:**
  - Pin GitHub actions to commit SHAs.
  - Pin pip-audit's own dependencies under `uvx`.

## Accepted risks

| Risk | Why it is acceptable | Accepted by |
|---|---|---|
| minimatch GHSA-g3hv-75wg-m249 (CVE-2026-118764): denial of service via globparts amplification (CWE-405), waived in `apps/web/pnpm-workspace.yaml` | It is reached only through eslint dev tooling, with globs the repo controls, and is never bundled. The fix (minimatch 11.0.1) is a major version eslint's tree does not accept. | Owner (Shreyan Dhawa), 2026-11-13. Remove the waiver once `pnpm why minimatch` shows no minimatch below 11.0.1; check on every eslint upgrade. |
| While the API runs, any page served at `http://localhost:5173` counts as an allowed origin, even one from another local dev server | Another local process is in the accepted single-user-machine stance until token mode. `strictPort` makes Nosolear fail loudly instead of moving to another port. | Falls under the single-user-machine stance the owner decided on 2026-11-12. The security review raised this residual on 2026-11-13; the owner has not confirmed it separately. |

## Licence notes (verified in Task 2, corrected in §17 by PR #27)

- CrisperWhisper: the code is MIT, and the weights are CC BY-NC 4.0 (`nyralabs/CrisperWhisper`, formerly `nyrahealth/`). The upstream README also names a Nyra non-commercial research licence, so 0d checks the licence of the revision it pins.
- `mlx-community/whisper-large-v3-turbo` declares no licence on its card. It is a conversion of OpenAI's MIT `large-v3-turbo`.
- espeak-ng is GPL-3.0 or later (release 1.52.0 when checked).

## Plans, in execution order

| Phase | File | Tasks | Branch prefix |
|---|---|---|---|
| 0b Open-source foundation (done) | `docs/superpowers/plans/2026-11-12-phase-0b-open-source-foundation.md` | 12 | `p0b/` |
| 0c Audio, jobs, ledger | `docs/superpowers/plans/2026-11-12-phase-0c-audio-jobs-ledger.md` | 11 | `p0c/` |
| 0d Provider adapters | `docs/superpowers/plans/2026-11-12-phase-0d-provider-adapters.md` | 13 | `p0d/` |
| 0e Scoring, calibration, baseline | `docs/superpowers/plans/2026-11-12-phase-0e-scoring-calibration-baseline.md` | 12 | `p0e/` |
| 1 Daily loop backend | `docs/superpowers/plans/2026-11-12-phase-1-daily-loop-backend.md` | 11 | `p1/` |

The Alembic chain after `main`'s 0003 (0b):
- 0004 (0c)
- 0005 `tts_cache` and 0006 `provider_capabilities` (0d)
- 0007 (0e)
- 0008–0011 (Phase 1)

## Decisions and why

| Date | Decision | Why |
|---|---|---|
| 2026-11-12 | Open source, bring your own keys, local only. No accounts, no hosting. | The owner changed direction. |
| 2026-11-12 | MIT licence. | Owner's choice. |
| 2026-11-12 | Localhost only. The token-auth mode is designed now and built in Phase 6, and phone access waits for it. Supported on single-user machines only until then. | Never expose the API unauthenticated. The web app can't send a token yet. |
| 2026-11-12 | macOS and Linux are first-class. Windows goes through WSL2. CI adds a macOS runner. | Owner's choice. The repo is public, so the runner is free. |
| 2026-11-12 | Approach A: one package. The local models are optional extras (`local`, `apple`) with lazy imports. | One process and one lockfile. Readiness says "not installed" rather than crashing. |
| 2026-11-12 | CrisperWhisper is opt-in only. | Its weights are licensed for non-commercial use only. |
| 2026-11-12 | Calibration uses the old S2 method in the app: ≥80% hits, ≤20% false alarms, at least 5 error tokens and 5 controls per key. It's skippable; until then, scores are provisional. Prosody isn't calibrated yet. | The goal: calibrate, then baseline, then daily practice. Prosody has no deliberate-error method yet. |
| 2026-11-12 | Scope is the old Phase 0 build plus the Phase 1 backend. After that: 2 web UI, 3 drills, 4 conversation, 5 progress (including daily skill scores), 6 token mode and phone access. | Goal item 6. |
| 2026-11-12 | The target accent is en-US, with the locale as a setting. The coach defaults to `claude-opus-5-5` and is configurable. Refusal fallbacks to a second model are off. | Earlier decisions. With no fallbacks, the ledger's upper-bound estimate stays valid. |
| 2026-11-12 | `NOSOLEAR_TIMEZONE` sets the daily plan's "today" (local midnight). Ledger cap periods stay in UTC. | Owner's choice: a Nepal user would otherwise see the day roll over at 05:45. |
| 2026-11-12 | One job worker by default (`NOSOLEAR_JOB_WORKERS`). | Azure F0 allows one concurrent request. |
| 2026-11-12 | API keys must be at least 16 characters. | So log scrubbing always applies. |
| 2026-11-12 | Whisper defaults: `small.en` on faster-whisper for CPU, `whisper-large-v3-turbo` on MLX. Both are configurable. | Speed on CPU-only machines. |
| 2026-11-12 | The `local-models` CI job is path-filtered and not a required check. | It's heavy and could be flaky. |
| 2026-11-12 | `GET /api/plan/today` is read-only; `POST` creates the plan. | §15: no GET request changes state or triggers a paid call. |
| 2026-11-12 | Keep `p0b/spikes`. Its code is salvaged into `apps/api` by the tasks that need it. | The owner's rule against deleting branches. That code is already debugged. |
| 2026-11-13 | The Vite proxy keeps the browser's Host header. The dev and preview servers are pinned to `localhost` with `strictPort`, and a config plugin refuses a non-loopback `--host`. | Security review S1: with the string proxy form, the API's DNS-rebinding check never saw the browser's Host. |
| 2026-11-13 | pnpm audit fails at moderate, and every waiver is an explicit GHSA id with a comment. pip-audit runs on ubuntu and macOS behind the `audit` gate. CI also runs weekly. | Security review S2 and S3. Vite's dev-server advisories are usually moderate, and pinned lockfiles change only when someone pushes. |
| 2026-11-13 | FastAPI's `/docs` and `/redoc` are off. | They load JavaScript from a CDN into the API's origin, and opening them contradicts §16. |
| 2026-11-13 | `HF_HUB_DISABLE_TELEMETRY` is always `1`, even when the user presets it. | §14 says the app sets it and it is not a user setting. The plan's `setdefault` was a defect. |

## Owner notes

- The default language pack is now `neutral`. A profile stored under Phase 0a is rebuilt with neutral priors on first start; set `NOSOLEAR_PACK=nepali` in `.env` to keep the 0a priors.
- `make web` and `vite preview` refuse a non-loopback `--host`. Never set Vite's `server.allowedHosts: true` or turn on `server.https` without a security review.

## Open questions for the owner

None.

## Branch and PR state

- `main`: "Record the owner's acceptance of the minimatch audit waiver" (this PR), after #30 "Update the handoff: Phase 0b is done and Phase 0c is next".
- `docs/phase-plans`: merged (#13) and kept.
- `p0b/01-community-files` … `p0b/11-planted-key-test`: merged (#14–#25) and kept. #24's squash subject on `main` is the branch name "p0b/10 readme setup guide", because `--fill` on a multi-commit PR uses the branch name. Later merges pass `--subject`.
- `p0b/12-licence-notes` (#27), `p0b/12-security-fixes` (#28), `p0b/12-final-review-fixes` (#29) and `p0b/12-phase-verification` (#30) and `p0b/12-accept-minimatch-waiver` (this PR): merged and kept.
- `docs/byok-architecture`: merged and kept (deleting branches needs the owner's approval).
- `p0b/spikes`: unmerged and kept. Everything is under `spikes/`, with no audio and no data.

## Adapters not yet verified against the live service

None are built yet, so every adapter in Phase 0d starts unverified. Live checks need the owner to put the Azure and Claude keys in `.env`; never ask for a key in chat. Update this list as live tests pass.

## Working rules carried forward

- Hand off at about 35–40% context, at a task boundary, and at the end of every phase.
- Commits: imperative sentence. No Co-Authored-By trailer. No "Generated with Claude Code" footer.
- Commit and push to the feature branch as you go. Never push to `main`. Squash-merge task PRs with `gh pr merge --squash --subject "<sentence> (#N)"` (no `--delete-branch`) once CI is green and a non-author reviewer approves. Gate PRs wait for the owner. `main`'s branch protection requires a PR with `enforce_admins` on; changing protection is the owner's call.
- Review seats (to protect the owner's Max limits):
  - Security-heavy tasks get the task reviewer plus pr-review-toolkit's silent-failure-hunter and pr-test-analyzer.
  - Other tasks get one sonnet task reviewer whose prompt adds error-handling and test-gap lenses.
  - Scoped re-reviews of small fix diffs can run on haiku.
  - Check `mcp__ccd_session_mgmt__get_usage` between tasks.
- The owner's `.env` holds a real Azure key and region. Never read or print it. Tests never load it (the autouse fixture in `apps/api/tests/conftest.py`). Tests marked `live` (run with `make test-live`) are exempt from that isolation and use the `live_settings`/`require_keys` helpers in `tests/live/`. Run walk-throughs in a temp clone with a temp `.env`, never the real one.
- Models: haiku for search, summaries and running tests; sonnet for well-specified implementation and routine review; opus for architecture, security review and final review. If a cheaper model fails review twice, re-dispatch on a stronger one.
- Ask the owner for anything that costs money, deleting branches or data, and approval gates.

## Verify the current state

```bash
make setup   # first time only: git hooks, uv sync, pnpm install
make test
make lint
```
