# Handoff

Read this first in a new session, then continue from **Next**.

## Current phase

Phase 0e (scoring, calibration, baseline) is done as of 2026-11-13. Phase 1 (daily loop backend) is in progress.

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
- 2026-11-13: Phase 0c Task 7: the step registry and interface for Phases 0d and 0e (`app/steps.py`: `Step`, `StepContext`, `StepRegistry`, `current_job_id`), `run_job` (`app/run_job.py`: plan order, BLOCKED and SKIPPED handling, typed errors kept, other exceptions as `internal_error` with type-only logging), the analysis store (`domain/analyses.py`, `ports/analyses.py`, `AnalysisRepository` with idempotent `put`), and the `FakeAnalysisStore`, `FakeStep` and `FakeProfileStore` fakes, plus the job leak surface.
- 2026-11-13: Phase 0c Task 8: the thread-pool job runner (`adapters/thread_pool_runner.py`), the `Services` composition root with `build_services`, `build_ledger` and read-only `read_usage` (`api/deps.py`), the jobs API with `ErrorOut` bodies and the typed-error handlers (`api/job_routes.py`, `api/errors.py`), startup recovery in the lifespan, and real usage figures in readiness and `nosolear doctor`.
- 2026-11-13: Phase 0c Task 9: the recording upload (`POST /api/attempts/{attempt_id}/recording`, raw `audio/wav`, streamed under the 10 MB cap into the data dir) through `app/upload_recording.py`, with `RecordingRepository` (the recording row and its ANALYZE job in one transaction) and `AttemptRepository` (`create_attempt`, `get`), the regenerated API types, and the SECURITY.md upload and data-at-rest lines.
- 2026-11-13: Phase 0c Task 10: the API client for the CLI (`cli_client.py`: `ApiClient` with streamed `upload_wav`, `get_job`, `resume_job` and `follow_job`, errors limited to `ErrorOut` messages and generic sentences), the `nosolear upload` and `nosolear job` commands (exit codes 0 done, 1 failed, 2 usage or upload error, 3 timeout), `--new-attempt` refusing the real data directory, and `httpx` moved to runtime dependencies.
- 2026-11-13: Phase 0c Task 11, phase verification:
  - Ran in a temp clone of `p0c/09-upload-cli` with no `.env`: `make test` (995 API, 31 web), `make lint`, `make gen-api` (no diff) and the heavy Hypothesis profile on `tests/domain` and `tests/persistence` (361) all pass.
  - Done-when by hand: `nosolear serve` plus `nosolear upload synthetic.wav --new-attempt` (a 2 s, 48 kHz sine) exits 0. The job ends `done` with every step `skipped (not_available)`. The file lands in `recordings/<uuid>.wav` at 16 kHz with mode 600, and `.incoming/` is empty. curl gets 415 for a wrong content type, 413 for `Content-Length` over 10 MB and 400 for garbage, and no error body holds a path. `git status` shows nothing under `data/`.
  - Cap check: with `NOSOLEAR_CAP_CLAUDE_TOKENS=10`, `Meter.call` over the real ledger raises `CapExceeded` and makes no call.
  - One combined opus security and final review over `a472f81..` the phase tip: 0 High, 0 Medium, 1 Low, 0 Critical, 2 Important. The fix PR (#35's later commits) covers both Important findings: `read_usage` no longer creates `-wal`/`-shm` files on a stopped database, and a job whose `run` raises is marked failed (so it can be resumed) instead of staying `running`. The same pass fixed six Minor findings: meter negative actuals, upload cleanup errors, non-JobOut CLI bodies, an early 409, the readiness wording, and the CLI skip reason. The rest are under "Carried to later phases".
- 2026-11-13: Phase 0d Task 1: the provider ports (`ports/providers.py`), the speech and coach result types (`domain/speech.py`, `domain/coach.py`), `RetryableProviderError` and `MalformedProviderResponse` in `domain/errors.py`, and the in-memory fakes in `tests/provider_fakes.py`.
- 2026-11-13: Phase 0d Task 2: the retry wrapper (`adapters/retry.py`: 1, 2, 4, 8 second backoff with injectable sleep, four `Retrying*` port wrappers), the audio-second estimator (`budget/estimators.py`), the metered Azure scorer and transcriber (`budget/metered_ports.py`), and `paid_scorer` and `paid_transcriber` in `api/deps.py`, ordered retry -> metered -> raw.
- 2026-11-13: Phase 0d Task 3: the Azure Speech client (`adapters/azure_speech.py`: one request at a time, `classify` to safe messages, the SDK loaded lazily through `_sdk()`), the escaped SSML and cache hash (`domain/ssml.py`), `azure_tts` with a one-time voice fallback (`adapters/azure_tts.py`), the clip cache and migration `0005_tts_cache` (`adapters/tts_cache.py`, `persistence/tts_cache.py`), TTS metering for both voices and `paid_speech_synthesizer` in `api/deps.py`, with `azure-cognitiveservices-speech==1.53.0` pinned.
- 2026-11-13: Phase 0d Task 4: the Azure pronunciation assessment, from the payload parser (`domain/results/azure_pa.py`: phoneme n-best, word and prosody feedback, weighted phrase scores, `NoMatch` as empty) to the raw scorer (`adapters/azure_pa.py`: scripted once with miscue up to 30 s, continuous otherwise, unscripted without a reference, IPA with five n-best phonemes), with the hand-written payload builders in `tests/adapters/azure_payloads.py`.
- 2026-11-13: Phase 0d Task 5: the Azure speech-to-text path: word timings cleaned for storage (`domain/results/words.py`), the transcript parser (`domain/results/azure_stt.py`), the raw `AzureTranscriber` in continuous mode with word timestamps (`adapters/azure_stt.py`), the transcriber choice (`domain/transcriber_choice.py`: explicit settings honoured with warnings, `auto` over the installed and measured-fast candidates, `azure_stt` always last), and `Transcriber` in `settings.py` now built from `TranscriberName`.
- 2026-11-13: Phase 0d Task 6: the `local` and `apple` extras with exact pins (lock resolved, all packages have cp314 wheels on macOS arm64 and Linux x86-64), the pinned model specs with full commit SHAs (`adapters/model_specs.py`), `ensure_model` with telemetry off and a fixed revision (`adapters/hf_models.py`), `LazyModel` with a 600 s idle unload (`adapters/lazy_model.py`), `local_env` (platform, installed libraries, devices, espeak-ng, all without importing a heavy library), the `local_models` marker and `make test-local-models`, and the `local-models` CI workflow (path-filtered, not a required check).
- 2026-11-13: Phase 0d Task 7: the local Whisper transcribers: the payload parser and the `parse_transcript` dispatcher (`domain/results/whisper.py`, `domain/results/__init__.py`), and the raw `faster_whisper`, `mlx_whisper` and opt-in `crisper_whisper` adapters, which load their libraries and models only on first use and turn library errors into literal `ProviderUnavailable`.
- 2026-11-13: Phase 0d Task 8: the phone symbols (`domain/phones.py`: the Azure en-US phone set, the salvaged map and `UnmappedSymbol`, and `split_espeak_ipa`) and the minimum-cost phone alignment (`domain/phone_alignment.py`). The espeak-ng sweep over the calibration words found no new symbol to map. Left unmapped for the owner, because no Azure phone is the same sound: `ɾ` (flap), `ᵻ`, `ɐ` and `ʔ`. Ruff's `allowed-confusables` now lists the IPA marks the map uses.
- 2026-11-13: Phase 0d Task 9: the wav2vec2 phone probe: the payload parser (`domain/results/phone_probe.py`) and the raw `Wav2Vec2EspeakProbe` (`adapters/wav2vec2_espeak.py`), which runs espeak-ng with a fixed argv and the text on stdin, decodes the CTC output greedily, and loads the pinned pickle checkpoint with `weights_only=True`. Its real-model and TTS tests are written but were not run (they need the extras and downloads).
- 2026-11-13: Phase 0d local-models fixes (`p0d/09-local-models-fixes`): the first real-model run showed three adapter bugs. The Whisper adapters now read the 16 kHz WAV into a float32 array (`adapters/wav_samples.py`) instead of passing a path, because faster-whisper's PyAV decode raised `TypeError` and mlx-whisper ran ffmpeg on a path. `espeak-ng --stdin` drops the last character of input without a trailing newline, so the probe's expected phones and the test fixture's audio were both truncated (`vest` came out `ves`); both now send a newline. The model test word `school` became `stop`, since the model hears espeak's final dark l as `v a` (a model limit, not a mapping gap); `vest` and `think` are unchanged. No symbol was added to `domain/phones.py`.
- 2026-11-13: Phase 0d Task 10: the Claude coach: the request builders, taxonomy-enum schema, quote verification and parsers (`domain/coach.py`, re-exported from `domain/results`), the raw `ClaudeCoach` over the Messages API with `anthropic==2.8.0` and `httpx2==2.16.0` pinned (`adapters/claude_coach.py`), `claude_tokens` and `MeteredCoach` (`budget/`), and `paid_coach` ordered retry -> metered -> raw in `api/deps.py`.
- 2026-11-13: Phase 0d Task 11: the composition root (`api/deps.py`: `RawPorts`, `Providers` and `build_providers`, one shared `Meter` that reads the running job id, `get_providers`), the four analysis steps (`app/analysis_steps.py`: score, transcribe, probe and coach, each reusing its stored analysis) registered for ANALYZE, and the SDK allow-list table in the import test. The HTTP and SDK loggers are pinned at WARNING in `prepare_process`.
- 2026-11-13: Phase 0d Task 12: the capability facts and readiness rows (`domain/capabilities.py`: staleness by region and locale, the newest speed figure per local transcriber, the Azure, transcriber and phone probe rows), the `provider_capabilities` table and migration `0006_provider_capabilities`, the Azure n-best and prosody probe (`adapters/azure_pa_probe.py`), the local speed check on a 161-word passage with warm-up untimed (`adapters/transcriber_speed_check.py`), `probe_capabilities`, and `nosolear doctor --probe`. Plain `doctor` reads the stored records read-only and creates nothing.
- 2026-11-13: Phase 0d review fixes (I1, I2, I3, M2, M10, M13): the coach ignores shell `ANTHROPIC_CUSTOM_HEADERS` and telemetry variables; the server's `auto` transcriber uses the stored speed figures as `doctor` does; `doctor --probe` reports every probe failure as a safe line (with leak surfaces for its output); a voice switches only on a `BadRequest` and only once the fallback is accepted, and a regenerated TTS clip replaces its cache row; live tests run the CLI's process setup; a whisper model setting must be a pinned model.

- 2026-11-13: Phase 0d phase review. One combined opus security and final pass over `acec2f4..21998ab` found 0 Critical, 3 Important and 13 Minor. The fix PR #41 covers:
  - all three Important findings: the coach ignores shell `ANTHROPIC_CUSTOM_HEADERS` and OTel variables; the server's `auto` transcriber uses the stored speed factors; `doctor --probe` turns every failure into a safe message and has leak-surface producers;
  - three of the Minor findings: TTS falls back only when the voice is rejected and upserts regenerated cache rows; live tests run `prepare_process`; the whisper model settings are checked against the pinned tables.

  The remaining Minor findings are under "Carried to later phases". The `local-models` job is green on Ubuntu and macOS since #40.
- 2026-11-13: Phase 0e Task 1: scoring configs in `domain/scoring.py` (`v0` rules, calibrated-config invariants, `rules_to_json`/`rules_from_json`, `current_observations` for the newest config per attempt), with `Observation` and `ProfileEntry` carrying `scoring_config_id`/`provisional`, and the seed stamped as `v0`.
- 2026-11-13: Phase 0e Task 2: migration 0007 adds `scoring_configs` (with the `v0` row), `calibration_runs`, `calibration_trials`, `content_items`, `skill_scores` and `extractions`, and scores every existing observation under `v0`; `ObservationRepository.current()` and `ProfileRepository` carry the config and `provisional`, and `GET /api/profile` returns `provisional`. Migrations now run with foreign keys off and check `foreign_key_check` after.
- 2026-11-13: Phase 0e Task 3: sound and prosody extraction in `domain/extraction/` (`phones.py`, `opportunities.py`, `sounds.py`): Azure n-best substitution, low-accuracy and prosody opportunities, and phone-probe substitution, epenthesis and final-cluster opportunities, all pure and tested with Hypothesis.
- 2026-11-13: Phase 0e Task 4: fluency and coach extraction (`fluency.py`, `coach.py`: untrusted findings re-checked against the transcript and the step) and the pure `extract` entry point that turns one attempt's typed results into observations under one scoring config, stamping `provisional` from the rule.
- 2026-11-13: Phase 0e Task 5: the analyze job's `extract` step writes each attempt's observations under the newest config and rebuilds the profile without a snapshot; `POST /api/rescore` (`startRescore`) and `nosolear rescore` re-score stored history with no provider port, and `ProbeStep` runs under `v0` only for calibration and drill attempts.
- 2026-11-13: Phase 0e Task 6: the seed content, validated before use: the calibration set (five words per key, 50 words, in `content/calibration/items.toml`) and the baseline protocol (`content/baseline/protocol.json`, a 164-word passage annotated for every SUB and LOW key and the epenthesis key). `domain/content.py` holds the types and validators, `adapters/content_files.py` loads them, and `ContentRepository` syncs them into `content_items` at startup (ids are immutable, retired seed rows stay readable).
- 2026-11-13: Phase 0e Task 7: the calibration rule in `domain/calibration.py` (integer-exact pass rule, trial tally, warnings for attempted-correct takes that never change enablement), `flagged` for one clip, `plan_calibration` (emphasis keys first, correct take before its deliberate takes) and `build_calibrated_config`, which writes calibrated key rules only for covered pairs.
- 2026-11-13: Phase 0e Task 8: the calibration session. `persistence/calibration_repository.py` (runs, a session of calibration attempts, trials and TTS control rows, one open run at a time), `app/calibrate.py` (start, skip, finish, view; refusals are safe 409 messages), `app/calibrate_job.py` (`controls` synthesizes and scores each word once through the composed ports, `evaluate` writes the flags and the calibrated config, `queue_rescore`), `POST/GET /api/calibration`, `POST /api/calibration/skip` and `/finish`, and `nosolear calibrate start|status|skip|finish`. Prosody is not calibrated in 0e (§9.2, §18).
- 2026-11-13: Phase 0e Task 9: per-skill scores (`domain/skill_scores.py`: linear anchors, the Sounds, On the spot and Articulate components, unavailable components omitted) and the ranked baseline report (`domain/baseline_report.py`: keys missed this session, clips from the session's own misses, the four honest notes).
- 2026-11-13: Phase 0e Task 10: the baseline session. `persistence/baseline_repository.py` (one session of kind `baseline` with one attempt per protocol item, scores, completion), `app/baseline.py` (start, view, complete with `BaselinePending`/`BaselineNotOpen`, the report, and the refresh of completed baselines), `POST/GET /api/baseline`, `POST /api/baseline/complete` and `GET /api/baseline/report`, `nosolear baseline start|status|complete|report`, and `RescoreStep` refreshing every completed baseline's snapshot and scores with no provider call.
- 2026-11-13: Phase 0e Task 11: onboarding and the first run. `domain/onboarding.py` (blocking readiness rows, `next_step`), `app/onboarding.py` and `GET /api/onboarding` (read-only), `nosolear onboarding` and the testing aid `nosolear stand-in calibration|baseline` (TTS audio through the metered, cached synthesizer, built only for that command). The first run is covered end to end through the API and the CLI with oracle providers, and a live twin in `tests/live` runs on real audio. The README has a First run section.
- 2026-11-13: Phase 1 Task 1: the selection policy in `domain/selection.py` (Thompson sampling per key seeded from the date, one focus per skill with the variety rule, a fallback from unseen defined keys, one re-check probe, unscored keys never chosen), with `RecheckState` in `domain/rechecks.py`.
- 2026-11-13: Phase 1 Task 2: the re-check schedule. `advance_rechecks` in `domain/rechecks.py` (the 2, 4, 8, 16, 32 day ladder, a relapsed key dropped), migration `0008_recheck_columns` adds nullable `profile_entries.next_recheck_at` and `recheck_stage`, `RecheckRepository` implements the `RecheckStore` port in `ports/plan.py`, and `ProfileRepository.save`/`replace` carry the schedule for keys still mastered.
- 2026-11-13: Phase 1 Task 3: daily plan assembly in `domain/daily_plan.py` (the fixed `PLAN_STEPS` protocol times, `choose_prompt` by focus and probe density with recent prompts avoided, one drill per focus with the taxonomy's drill family, and the seeded `assemble_plan`), all pure and covered by Hypothesis properties.

- 2026-11-13: Phase 1 Task 4: `build_daily_plan` (`app/build_daily_plan.py`) builds today's plan once per local date in `NOSOLEAR_TIMEZONE`, then returns the stored one. Migration `0009_daily_plans` and `DailyPlanRepository`, `PromptBankRepository` and `ScoringCoverage` (`persistence/plan_repositories.py`) store it with its prompt text and seed, so a retired prompt keeps its plan.
- 2026-11-13: Phase 1 Task 5: the plan API and CLI. `POST /api/plan/today` (`buildTodayPlan`) builds the local day's plan (201, then 200 on repeat) and `GET /api/plan/today` (`getTodayPlan`) only reads it (404 `no_plan_for_today`); sampled scores stay out of `PlanOut`. `nosolear plan [--json]` prints one line per focus, the probe, the prompt (control and bidi characters stripped) and the step list. The web contract is regenerated.
- 2026-11-13: Phase 1 Task 6: the daily session. `app/start_daily_session.py` builds or fetches today's plan and starts its one session (kind `daily`, `plan_id` unique, migration `0010_sessions_plan_id`) with one unscripted `speak` attempt whose content item is the plan prompt; `POST /api/plan/today/session` (`startDailySession`, 201 then 200) and `nosolear daily start` print the ids and the prompt, and the recording goes through the existing attempt upload path.
- 2026-11-13: Phase 0e phase review. One combined opus pass over `3b8e6ee..8a7d3ab` found 0 Critical, 3 Important and 10 Minor. The fix PR covers all three Important findings: baseline start and complete are serialized (check and create in one `BEGIN IMMEDIATE`, complete as a guarded claim), the baseline report skips an undecodable transcript, and leak-surface producers cover rescore, calibrate, stand-in and the calibrate job. It also fixes three Minor ones: a racing calibration start returns the open run, calibrate steps act on their own run, and a failed complete reopens the session. The rest are under "Carried to later phases".

## In progress

- Phase 1 is running under the budget rule: Tasks 1–3 are merged (#46) and Tasks 4–6 are on `p1/04-plan-api-session`. Its ledger is at `.superpowers/sdd/2026-11-12-phase-1-daily-loop-backend/progress.md` (git-ignored).
- Phase 0e is merged: #42 (Tasks 1–2), #43 (Tasks 3–5), #44 (Tasks 6–8), #45 (Tasks 9–11), and this PR (the review fixes and the close-out). Its ledger and review findings are in `.superpowers/sdd/2026-11-12-phase-0e-scoring-calibration-baseline/`. The 0c, 0d and 0e ledgers may be deleted.

## Next

1. Finish Phase 1: `docs/superpowers/plans/2026-11-12-phase-1-daily-loop-backend.md`, branch prefix `p1/`, under the budget rule. Tasks 7–10 remain, then Task 11 (verification), one opus review and one fix dispatch.
2. Owner:
   - Run `make test-live` with keys in `.env`; see "Adapters not yet verified against the live service".
   - Read the baseline passage (`content/baseline/protocol.json`) aloud once. It passes the validator, but nobody has reviewed it.
3. Any task that adds a dependency reruns `uv run --project apps/api python scripts/third_party_licences.py`.
4. At the end of each phase, run one combined opus security and final review over the phase range, then one fix dispatch. Then update this file and hand off to a fresh session.

## What Phase 1 and later can rely on (from Phase 0e)

- The 0e plan's "Produces for later phases" section, as shipped, with the deviations in the implementer reports in the 0e ledger.
- End-to-end tests use `make_harness` (`tests/harness.py`).
- `ScoringConfigRepository.newest()`, `rule_for` and `current_observations` are in `domain/scoring.py`.
- `rebuild_profile(..., session_id=, reason=)`.
- `content_items` and `attempts.content_item_id` exist.
- The migration head is 0007.
- `BaselineRepository.create` returns the open session if there is one, and `complete` is a guarded claim.
- A calibrate job carries an attempt id that belongs to its run.

## What Phase 0e and later can rely on (from Phase 0d)

The 0d plan's "Produces for later phases" section is accurate as shipped, with these differences:
- `create_app` also keeps 0c's `clock=None`.
- The whisper model settings accept only the pinned names.
- `capability_rows` takes `azure_ready`, `installed` and `auto_fix`.
- `build_services` passes the stored real-time factors, so the server's `auto` choice matches `doctor`.
- Provider fakes are in `tests/provider_fakes.py`. Payload builders are in `tests/adapters/azure_payloads.py` and `tests/adapters/anthropic_payloads.py`.

## What Phase 0d and later can rely on (from Phase 0c)

- `nosolear.domain.errors`: `NosolearError(message=None)` (`code`, `safe_message`, `str(e) == e.safe_message`), `InvalidAudio(reason)`, `CapExceeded`, `ProviderUnavailable`, `RequestNotSent(ProviderUnavailable)`, `CapabilityMissing`. 0d adds `RetryableProviderError` and `MalformedProviderResponse` here.
- `nosolear.ports.audio`: `AudioStore.begin_upload() / read(path) -> bytes / resolve(path) -> Path / delete(path)`; `Recording`, `StoredRecording`; `RecordingStore.for_attempt(attempt_id) -> Recording | None`; `AttemptReader.exists / get(attempt_id) -> AttemptInfo | None` (steps in 0d/0e find the audio with `for_attempt`, then `AudioStore.resolve`). Audio on disk is always 16 kHz mono 16-bit.
- `nosolear.domain.budget`: `Provider` (`azure`, `anthropic`: the provider ids every phase uses), `Unit` (`audio_seconds`, `tts_chars`, `tokens`), `Caps`, `ceil_seconds`, `Usage`. `nosolear.ports.ledger.UsageLedger.reserve / record / release / settle_open_reservations / usage`. `api/deps.py`: `build_ledger(settings, engine, *, clock=None)`, `read_usage(settings)`.
- `nosolear.budget.meter`: `Meter(ledger, job_id=current_job_id).call(provider, unit, estimate, fn, actual)`, `metered_method(meter, provider=, unit=, estimate=, actual=)`. `nosolear.budget.compose`: `PortWrapper` (class attribute `layer`, attribute `inner`; raw adapters declare `layer = "raw"`), `compose_paid_port(raw, metered=, retry=, cache=None)`, `layers_of(port)`. `build_paid_ports` is replaced by 0d's `build_providers(...).paid_ports()`; `test_deps_composition.py` and `RAW_ADAPTER_MODULES` in `test_no_unmetered_sdk_imports.py` are extended by 0d.
- Jobs: `JobKind` (`analyze`, `rescore`; 0e adds `calibrate` with its plan), `JobQueue.enqueue(kind, attempt_id | None) -> Job`, `resume`; `JOB_PLANS` (analyze: `score, transcribe, probe, coach, extract`; rescore: `extract`; `coach` needs `transcribe`; `extract` uses all analysis steps).
- Step interface (`nosolear.app.steps`): `Step.name`, `Step.applies(ctx) -> bool`, `Step.run(ctx) -> None`, `StepContext(job_id, kind, attempt_id, progress)`, `StepRegistry.register(kind, step)`, `current_job_id()`. Steps must be idempotent, look up their own analysis first, and write results with `AnalysisStore.put(NewAnalysis(...))`.
- `nosolear.ports.analyses.AnalysisStore.get / put / for_attempt` over the `analyses` table; `NewAnalysis.adapter_version` is an int. Control rows keyed by `tts_hash` and `calibration_run_id` are supported by the schema; 0e adds their port methods and foreign keys.
- API: `POST /api/attempts/{attempt_id}/recording`, `GET /api/jobs/{job_id}`, `POST /api/jobs/{job_id}/resume`, `ErrorOut{code, message}` for every typed error (later phases use the same body); `create_app(settings, *, step_registry=None, start_runner=True, ledger=None, clock=None)`; `Services`, `build_services`, `get_services`, `get_clock`; `ThreadPoolJobRunner.run_pending()`.
- Test helpers: `tests/fakes.py` (`FakeAudioStore`, `FakeUsageLedger`, `FakeJobQueue`, `FakeAnalysisStore`, `FakePaidPort`, `FakeStep`) and `tests/wavs.py` (`make_wav`, `raw_wav`). Migration `0004_recordings_jobs_ledger`.
- CLI: `nosolear.cli_client.ApiClient` (`get_json`, `post_json`, `upload_wav -> job id`, `get_job`, `resume_job`, `follow_job -> final body`), `CliError`, `CliTimeout`; `cli.main(argv, *, client=None)`; `nosolear upload`, `nosolear job`; `AttemptRepository.create_attempt(...)` (dev convenience; 0e and Phase 1 create their own sessions and attempts).

Cross-phase assumptions (from the 0c plan): None open: 0b's settings tree (including `job_workers`), `make_settings`, `loopback_client`, readiness and `make test-live` are named as 0b produces them.

## What later phases can rely on (from Phase 0b)

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

- **Phase 0c:** done. The lifespan's adapter construction moved into `build_services` (the engine is disposed on any startup error), `cli.py` has no `assert pack`, `tests/fakes.py` has `FakeProfileStore`, and SECURITY.md states the upload checks and the data-at-rest stance.
- **From the Phase 0c review, for Phase 0d:**
  - Build the shared `Meter(ledger, job_id=current_job_id)` in the composition root when the first paid port lands. `Meter`'s default `job_id` is `lambda: None`, so ledger rows silently lose their job id if this is forgotten.
  - A crash between `AudioStore` storing a file and `add_and_enqueue` committing leaves an unreferenced `recordings/<uuid>.wav`. Add a startup sweep or accept it.
  - `test_reserve_takes_write_lock_before_reading` would also pass for a read-then-write ledger. Assert with a `before_cursor_execute` listener that no SELECT ran before the lock.
  - Add a route test for a client disconnecting mid-upload (`.incoming/` empty afterwards).
  - Smaller items:
    - `follow_job`'s timeout counts polls, not wall-clock time.
    - `InvalidAudio` does not survive pickling.
    - The WAV chunk walker has no chunk-count cap.
    - `test_parse_never_raises_anything_but_invalid_audio` should get a structured strategy.
    - `encode_wav` with NaN or inf floats is an undefined cast.
    - `test_busy_timeout_is_set` cannot fail, because sqlite3 already defaults to 5000 ms.

- **From the Phase 0d review (deferred Minors, `phase-review-findings.md` in the 0d ledger):**
  - M1: Azure SDK calls are not wrapped. An SDK `RuntimeError` becomes `internal_error` and is recorded at the full estimate even when nothing was sent. Map pre-send failures to `RequestNotSent` and the rest to `ProviderUnavailable`.
  - M3: every retried 429 records the full estimate (as §11 says). A coach rate-limit burst can use most of a day's token cap. This is an owner decision, since it would change the spec.
  - M4: `speak_ssml_async().get()` and `recognize_once()` have no overall timeout and hold the process-wide Azure lock. On a 120 s clip, retries can hold it for about 22 minutes.
  - M5: `mlx_whisper` calls `ensure_model` (a Hub metadata request) on every transcription and never unloads.
  - M6: real-time-factor records are not tied to the model or library version. Azure staleness ignores a key or tier change in the same region.
  - M7: one malformed coach finding fails the whole analysis instead of being dropped and counted.
  - M8: `test_coach_reserves_upper_bound` never asserts that the reservation equals `claude_tokens(request)`.
  - M11: `FREE_TALK_SCORING = CONTINUOUS` cannot take effect while `JOB_PLANS` runs `score` before `transcribe`. Fix the order when the free-talk decision lands.
  - M12: the Azure lock is per process, so `doctor --probe` during server jobs can put two requests in flight on F0.
  - Phone probe: `a` (heard between `æ` and `ɑ`) is unmapped, and `ɾ`, `ᵻ`, `ɐ` and `ʔ` were seen before the espeak newline fix. `θ` is heard as `s`, and espeak's dark final `l` is heard as `v a`, so the local-models test word `school` became `stop`. The map still fails loudly on unknown symbols (§4).
  - The Azure Speech SDK's licence is listed as "Other/Proprietary" in `THIRD_PARTY_NOTICES`; the owner should read its terms. The SDK has its own telemetry with no switch in its Python API (PRIVACY.md says so). Sixteen Linux-only NVIDIA wheel rows say "verify on the wheel".
- **From the Phase 0e review (deferred Minors, see `phase-review-findings.md` in the 0e ledger):**
  - `finish_calibration` can queue two calibrate jobs. This is harmless.
  - The 0007 downgrade fails on any database that has run calibration.
  - The 0007 `provisional` backfill marks phone-probe sound rows provisional, which disagrees with `rule_for`.
  - The newest-config rule works per attempt, not per detector, during a partial rescore.
  - The calibration Hypothesis strategy rarely reaches covered pairs.
  - A retest baseline can send onboarding back to calibration.
  - The stand-in command migrates the live database and never disposes its engine.
  - From the fix: a start during the brief complete window can open a second session, and if that complete then fails, `reopen()` declines.
- **Still open from the 0b list for 0d (not done in 0d):** register derived credentials (Azure `issueToken` JWTs) with the scrubber if one is ever used; a scrubbing `sys.excepthook` in `prepare_process`; run the leak harness with SDK DEBUG logging on; base64 forms in `secret_forms`; guard `install_secret_scrubbing` against recursion; flag unknown `NOSOLEAR_*` names in `.env`; report a data dir that is a file or belongs to another user as not ready; README "what leaves your machine" for `doctor --probe` and `make test-live`; make PRIVACY.md's test check each row against §16. Done in 0d: logger pins at WARNING, the `Transcriber` alias unified with `TranscriberName`, the licence script's extras rows, and the CrisperWhisper licence check (nyralabs, CC BY-NC 4.0).
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
- **Unmapped phone symbols (for the owner), left unmapped on purpose:** `domain/phones.py` still raises `UnmappedSymbol` for them, which the probe reports as unavailable. `a` (open front vowel) was heard from wav2vec2 on espeak audio of `school` and `vest`; it sits between Azure's `æ` and `ɑ`, so there is no defensible single mapping. The first CI run also reported `ɾ` (flap, a t/d allophone), `ᵻ` (espeak's reduced `ɪ`), `ɐ` (between `ə` and `ʌ`) and `ʔ` (glottal stop, no Azure phone); those came from truncated input and did not reproduce after the newline fix. Decide per symbol, with a calibration sample, whether to map it or to drop it before alignment; `ᵻ` to `ɪ` is the likeliest to be defensible. Also: wav2vec2 hears `θ` as `s` on espeak audio, so calibration on `sound.sub.θ.s` may see false alarms.

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
| 0c Audio, jobs, ledger (done) | `docs/superpowers/plans/2026-11-12-phase-0c-audio-jobs-ledger.md` | 11 | `p0c/` |
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
| 2026-11-13 | Budget rule for 0c through Phase 1: finish within two 5-hour Max windows. Implementers are haiku by default and sonnet only after a haiku failure. Tasks are batched into a few PRs per phase. There are no per-task reviews or re-reviews: CI plus the implementer's tests are the gate. Each phase ends with one combined opus security and final review, then one fix dispatch. | Owner, 2026-11-13: "Finish it in 2 usage windows max.. cut down on checks", for all of 0c to Phase 1. |
| 2026-11-13 | `read_usage` opens the database read-only (`immutable=1` when no WAL file exists), so `doctor` creates no file. | Phase 0c review: `mode=ro` alone created `-wal`/`-shm` files on a stopped database. |
| 2026-11-13 | When `run_job` itself raises, the runner marks the job failed with `internal_error` on a best-effort basis. | Phase 0c review: otherwise the job stays `running`, cannot be resumed, and only a restart recovers it. |

## Owner notes

- Phase 0c is usable end to end with fake steps: `nosolear serve`, then `nosolear upload FILE --new-attempt` with `NOSOLEAR_DATA_DIR` set to a separate dir. `--new-attempt` refuses the real `data/`. Real analysis arrives with Phase 0d.
- The Phase 0c verification run stopped its test server with `pkill -f "nosolear serve"`, which would also stop any other `nosolear serve` that was running then.
- The default language pack is now `neutral`. A profile stored under Phase 0a is rebuilt with neutral priors on first start; set `NOSOLEAR_PACK=nepali` in `.env` to keep the 0a priors.
- `make web` and `vite preview` refuse a non-loopback `--host`. Never set Vite's `server.allowedHosts: true` or turn on `server.https` without a security review.

## Open questions for the owner

None.

## Branch and PR state

- `main`: Phase 0d merged through #41, after #36–#40.
- `p0d/01-ports-wrappers` (#36), `p0d/03-azure` (#37), `p0d/06-local-models` (#38), `p0d/10-coach-composition` (#39), `p0d/09-local-models-fixes` (#40) and `p0d/14-review-fixes` (#41): merged and kept. Local `worktree-agent-*` branches were left by subagent worktrees; they hold no unmerged work, and deleting them is the owner's call.
- `p0c/01-audio-domain` (#32), `p0c/02-audio-store` (#33), `p0c/06-jobs` (merged through #34), `p0c/08-runner-api` (#34) and `p0c/09-upload-cli` (#35): merged and kept.
- `docs/phase-plans`: merged (#13) and kept.
- `p0b/01-community-files` … `p0b/11-planted-key-test`: merged (#14–#25) and kept. #24's squash subject on `main` is the branch name "p0b/10 readme setup guide", because `--fill` on a multi-commit PR uses the branch name. Later merges pass `--subject`.
- `p0b/12-licence-notes` (#27), `p0b/12-security-fixes` (#28), `p0b/12-final-review-fixes` (#29) and `p0b/12-phase-verification` (#30) and `p0b/12-accept-minimatch-waiver` (#31): merged and kept.
- `docs/byok-architecture`: merged and kept (deleting branches needs the owner's approval).
- `p0b/spikes`: unmerged and kept. Everything is under `spikes/`, with no audio and no data.

## Adapters not yet verified against the live service

Phase 0e adds two live checks: `tests/live/test_first_run_live.py` (onboarding, calibration and baseline on real Azure and Claude), and calibration on the user's own voice. Calibration has only been run with the test oracle and fakes. The oracle also flags TTS controls, so calibration tests use a clean voice.

Every Phase 0d adapter has contract tests only, unless noted. Live checks need the owner to put the Azure and Claude keys in `.env` and run `make test-live`; never ask for a key in chat. Update this list as live tests pass.

| Adapter | What only a live run shows | Verified keylessly instead |
|---|---|---|
| `azure_tts` | Real SDK calls, the configured voice and the Ava fallback, whether Azure answers an unknown voice with BadRequest (the fallback relies on it), word boundaries, the slow rate | Contract tests |
| `azure_pa` | Real JSON field names; whether this tier returns n-best phonemes and prosody; scripted, continuous and unscripted modes | Contract tests |
| `azure_stt` | Detailed output, word timings, raw profanity | Contract tests |
| Free-talk scoring decision (§4, §18) | The unscripted versus transcribe-then-score comparison | None; stays open |
| `claude_coach` | Structured output on the user's model; real usage numbers; that the API accepts `anthropic==2.8.0`'s `Authorization: Bearer` for an API key; that clearing the SDK's private `_custom_headers` still holds on SDK upgrades | Contract tests over `MockTransport` |
| `AzureCapabilityProbe`, `doctor --probe` | The probe against the user's resource | Fakes only |
| `faster_whisper`, `mlx_whisper` (macOS), `wav2vec2_espeak` | Accuracy on TTS audio | CI `local-models` on espeak-ng audio, green on Ubuntu and macOS (PR #40) |
| `crisper_whisper` | Everything: gated download, word timings, speed | Contract tests only; never in CI. Opt-in (`NOSOLEAR_TRANSCRIBER=crisper_whisper`, licence accepted on Hugging Face) |
| Every live check | Linux | Only on the owner's macOS machine unless the owner runs `make test-live` on Linux |

## Working rules carried forward

- Hand off at about 35–40% context, at a task boundary, and at the end of every phase.
- Commits: imperative sentence. No Co-Authored-By trailer. No "Generated with Claude Code" footer.
- Commit and push to the feature branch as you go. Never push to `main`. Squash-merge task PRs with `gh pr merge --squash --subject "<sentence> (#N)"` (no `--delete-branch`) once CI is green (no per-task review under the budget rule). Gate PRs wait for the owner. `main`'s branch protection requires a PR with `enforce_admins` on; changing protection is the owner's call.
- Budget rule (owner, 2026-11-13; applies to 0d, 0e and Phase 1): fit the remaining phases into two 5-hour Max windows, counted from 2026-11-13.
  - Implementers are haiku by default and sonnet only after haiku fails a task.
  - Tasks are batched into a few PRs per phase, by layer or dependency chain.
  - There are no per-task reviews and no re-reviews. Each PR's gate is the implementer's tests plus green required CI.
  - Each phase ends with one combined opus security and final review, then one fix dispatch with no re-review. Minor findings are deferred to this file.
  - Check `mcp__ccd_session_mgmt__get_usage` after each batch. If the budget runs out, stop at a clean boundary, update this file and report.
  - Hand-off briefs carry this rule forward.
- Pipelining: the next batch branches from the previous batch's branch while that PR is in CI. After the squash-merge, merge `origin/main` into it (never force-push). Conflicts from the squash resolve to the branch side, because the branch already contains the merged commits.
- CI's ruff sorts `nosolear` as first-party, and a local ruff cache can hide an I001. Run `uv run ruff check --no-cache` before pushing.
- The owner's `.env` holds a real Azure key and region. Never read or print it. Tests never load it (the autouse fixture in `apps/api/tests/conftest.py`). Tests marked `live` (run with `make test-live`) are exempt from that isolation and use the `live_settings`/`require_keys` helpers in `tests/live/`. Run walk-throughs in a temp clone with a temp `.env`, never the real one.
- Models: haiku for search, summaries and running tests; sonnet for well-specified implementation and routine review; opus for architecture, security review and final review. If a cheaper model fails review twice, re-dispatch on a stronger one.
- Ask the owner for anything that costs money, deleting branches or data, and approval gates.

## Verify the current state

```bash
make setup   # first time only: git hooks, uv sync, pnpm install
make test
make lint
```
