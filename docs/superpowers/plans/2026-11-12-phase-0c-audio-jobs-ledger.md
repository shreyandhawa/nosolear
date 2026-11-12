# Phase 0c: Audio, Jobs, Ledger: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A WAV posted through the API or the CLI is validated, resampled to 16 kHz and stored under a server-generated name. A background job then runs it through a step pipeline (fakes in this phase) with visible progress, survives a restart, and every paid call is reserved against a usage cap before it is made.

**Architecture:** Pure WAV parsing, validation and resampling live in `domain/audio.py` (Hypothesis-tested). `AudioStore`, `JobQueue`, `UsageLedger` and `AnalysisStore` are Protocol ports with SQLite or filesystem adapters, composed in `api/deps.py`. A `run_job` use case walks a per-kind step plan through a `StepRegistry` that Phases 0d and 0e fill in. A small in-process thread pool claims jobs from SQLite, so a restart simply re-queues what was running. A generic `Meter` reserves, calls and records around any paid call, and paid ports are composed cache → retry → metered → raw.

**Tech Stack:** Python 3.14, FastAPI 0.162.4, SQLAlchemy 2.1.8 (SQLite, WAL), Alembic 1.20.1, numpy (already locked via scipy, now a direct pin), httpx 0.28.1 (moves from dev to runtime for the CLI), pytest 9.2.0, Hypothesis 6.170.15, ruff 0.17.4, pyright 1.1.414.

**Spec:** [docs/ARCHITECTURE.md](../../ARCHITECTURE.md): §13 (Phase 0c scope and done-when) is authoritative; also §3 (ports, packaging), §7 (data model), §8.1 (one recording), §11 (ledger), §14 (settings), §15 (threat table), §12 (testing).

## Global Constraints

- **Python:** `requires-python = ">=3.14,<3.15"`. Every new dependency is pinned exactly (`==`) and `uv.lock` is updated in the same commit. Heavy local-model dependencies stay in the optional extras `local` and `apple` (§3); this phase adds none.
- **Commands (run from `apps/api`):** `uv run pytest -q`, `uv run ruff check`, `uv run ruff format --check`, `uv run pyright` (strict for `src`). From the repo root: `make test`, `make lint`, `make gen-api`.
- **TDD for every change:** failing test first, run it, minimal code, run it, commit.
- **Layering:** `domain` has no I/O and imports no SQLAlchemy, FastAPI or filesystem code. Adapters are chosen only in `apps/api/src/nosolear/api/deps.py`. Every port has a fake in `apps/api/tests/fakes.py` (the repo's `factories.py` stays for domain builders). Domain errors are `ValueError` subclasses.
- **Hypothesis:** profiles `default` (100 examples) and `heavy` (1000, `HYPOTHESIS_PROFILE=heavy`) already exist in `tests/conftest.py`. Domain logic gets properties, not only examples.
- **Never commit audio or anything under `data/`.** All test audio is synthesized in memory (numpy tones) and never contains a real voice. `scripts/check-no-personal-data.sh` runs in CI and pre-commit.
- **Upload rules (§8.1, §15):** raw `audio/wav` body (not multipart) read through `request.stream()`; cap 10 MB (`10 * 1024 * 1024` bytes) checked from `Content-Length` up front and again while streaming; duration at most 120 s computed from frames actually received; exactly one `fmt` and one `data` chunk, 16-bit PCM (format tag 1), mono; sample rate in {16000, 22050, 24000, 32000, 44100, 48000}; the temp file lives inside the data dir (never the system temp dir); stored as `recordings/<uuid>.wav` (server-generated, 16 kHz); no path ever comes from user input; failures are `InvalidAudio` and the temp file is deleted.
- **Ledger rules (§11):** `reserve` before every paid call inside one `BEGIN IMMEDIATE` transaction; pass only if recorded + open reservations + estimate ≤ cap for the period; a call that fails before its request is sent releases; any other failure is recorded at the estimate; a reservation left open by a crash is settled at its estimate at startup, never released. Periods are UTC: Azure per calendar month (`YYYY-MM`), Claude per day (`YYYY-MM-DD`). Defaults: `NOSOLEAR_CAP_AZURE_AUDIO_HOURS=4.5`, `NOSOLEAR_CAP_AZURE_TTS_CHARS=450000`, `NOSOLEAR_CAP_CLAUDE_TOKENS=100000`.
- **Composition order (§11, §15):** every paid port is `cache → retry → metered → raw adapter` (cache for TTS only). Only raw adapter modules import provider SDKs.
- **Errors (§8.1):** the four typed errors `InvalidAudio`, `CapExceeded`, `ProviderUnavailable`, `CapabilityMissing`, each with a safe message. Provider error bodies and keys never reach job status, logs, API responses or OpenAPI.
- **Security rules (owner's, apply throughout):** keys come only from env or `.env` and never appear in logs, responses, errors or fixtures; bind 127.0.0.1; uploads cap size and duration, validate the WAV, generate file names server-side and write only under the data dir; check the ledger before every paid call; no telemetry.
- **apps/web:** the only permitted change is regenerating API types with `make gen-api` (commit the regenerated files) in any task that changes the OpenAPI schema, so CI's `contract` check stays green.
- **Git:** one branch and one PR per task, named `p0c/NN-<slug>`, branched from up-to-date `origin/main`. Imperative commit messages, no Co-Authored-By trailer, no "Generated with Claude Code" footer. Never push to `main`. Squash-merge only when CI is green: `gh pr merge --squash`, without `--delete-branch` (the owner approves branch deletions).
- **HANDOFF:** every task's PR updates `docs/superpowers/HANDOFF.md` (done / in progress / next, and adapters still unverified against the live service; Phase 0c builds no live adapters, so that list does not change).
- **Built on 0b:** tests build settings with `make_settings(...)` (`Settings(_env_file=None, ...)`, so a developer's `.env` never leaks in) and API clients with `loopback_client(app)` (0b's guards refuse TestClient's default host and peer). Every new `GET /api/...` route is added to `READ_ONLY_GET_ROUTES` in `tests/api/test_guards.py`. `create_app` keeps 0b's guard and CORS middleware; this phase adds parameters and lifespan steps, never replaces them.
- **Migration:** `0004_recordings_jobs_ledger` (`revision = "0004"`, `down_revision = "0003"`). The chain across phases is 0003 (0b), 0004 (0c), 0005–0006 (0d), 0007 (0e), 0008–0011 (Phase 1).

## Review Focus

Inputs and failure modes the spec implies that the obvious tests skip. Each has a test pinned in its owning task.

1. **A header that lies about the data.** Declared `data` length larger than the bytes received (truncated upload, or `0xFFFFFFFF` from a streaming encoder), declared length smaller than the file, or a wrong RIFF size. Duration comes from frames actually received; a 2 s body with a header claiming 100 s is a 2 s recording, and a body of zero frames is `InvalidAudio`. Task 1 (`test_duration_uses_frames_received`, `test_header_lies_never_crash`).
2. **Sample rate 0 and non-whitelisted rates.** The salvaged resampler divides by the rate. A header with rate 0, 1, 8000 or 96000 must be `InvalidAudio("bad_sample_rate")`, never `ZeroDivisionError` or a 500. Task 1 (`test_rate_zero_is_invalid_audio`), Task 9 (route test).
3. **A client that lies about `Content-Length`.** A small declared length with a huge body, a missing header with a chunked body, a non-numeric header. The cap is enforced while streaming, the response is 413 or 400 with a safe message, and no temp file is left in the data dir. Task 2 (`test_write_past_cap_aborts`), Task 9 (`test_lying_content_length_is_capped_while_streaming`).
4. **A crash or restart mid-job.** A job left `running` with a step `running` returns to the queue, finishes, and does not double-store its analyses; an open reservation from the crash is settled at its estimate. Task 6 (`test_requeue_running_resets_running_steps`), Task 7 (`test_resumed_job_does_not_repeat_done_steps`), Task 8 (`test_restart_finishes_interrupted_job`), Task 4 (`test_orphans_settle_at_estimate`).
5. **Two callers racing for the last of a cap.** Threads that both see headroom must not both pass, in any order of reserve, record and release. Task 4 (`LedgerMachine` stateful property, `test_threads_cannot_overspend`).

## Not in This Plan

- Real provider adapters, retry wrapper internals, estimators per adapter, capability probes, TTS cache (Phase 0d). This plan builds the generic `Meter`, `PortWrapper` and composition helper they plug into.
- Extraction, scoring configs, calibration, `GET /api/onboarding` (Phase 0e). The `extract` step is registered by 0e.
- Any UI, recording playback route, or `apps/web` change beyond regenerated types.

## File Map

```
apps/api/pyproject.toml                       + numpy, httpx moved to runtime deps (exact pins)
apps/api/src/nosolear/
  domain/errors.py                            NosolearError, InvalidAudio, CapExceeded, ProviderUnavailable, RequestNotSent, CapabilityMissing
  domain/audio.py                             limits, parse_wav, resample_to_16k, to_16k, encode_wav, check_declared_length
  domain/budget.py                            Provider, Unit, Caps, period_for, headroom, ceil_seconds, Usage
  domain/jobs.py                              JobKind, JobStatus, StepState, StepSpec, JOB_PLANS, StepRecord, Job, resume_plan
  domain/analyses.py                          AnalysisKind, NewAnalysis, StoredAnalysis
  ports/audio.py                              AudioStore, PendingUpload, StoredRecording, Recording, RecordingStore
  ports/ledger.py                             UsageLedger, Reservation
  ports/jobs.py                               JobQueue
  ports/analyses.py                           AnalysisStore
  adapters/filesystem_audio_store.py          FilesystemAudioStore
  adapters/thread_pool_runner.py              ThreadPoolJobRunner
  budget/meter.py                             Meter, metered_method
  budget/compose.py                           PortWrapper, compose_paid_port, layers_of
  app/steps.py                                Step, StepContext, StepRegistry, current_job_id
  app/run_job.py                              run_job use case
  app/upload_recording.py                     upload_recording use case
  persistence/models.py                       + recordings, jobs, usage_ledger, analyses
  persistence/migrations/versions/0004_recordings_jobs_ledger.py
  persistence/db.py                           + PRAGMA busy_timeout
  persistence/ledger.py                       SqliteUsageLedger
  persistence/job_queue.py                    SqliteJobQueue
  persistence/repositories.py                 + RecordingRepository, AnalysisRepository, AttemptRepository
  api/deps.py                                 + Services, build_services, build_ledger, build_paid_ports, getters
  api/app.py                                  lifespan starts/stops the runner; includes new routers
  api/errors.py                               NosolearError -> HTTP mapping
  api/recording_routes.py                     POST /api/attempts/{attempt_id}/recording
  api/job_routes.py                           GET /api/jobs/{job_id}, POST /api/jobs/{job_id}/resume
  api/schemas.py                              + UploadAcceptedOut, JobOut, StepOut, ErrorOut
  cli_client.py                               ApiClient (httpx), CliError
  cli.py                                      + upload, job commands; main(argv, *, client=None)
apps/api/tests/
  wavs.py                                     make_wav, raw_wav (synthetic WAV factory every later phase uses)
  fakes.py                                    FakeAudioStore, FakeUsageLedger, FakeJobQueue, FakeAnalysisStore, FakePaidPort, FakeStep
  domain/test_audio.py, test_audio_properties.py, test_budget.py, test_jobs.py, test_jobs_properties.py
  adapters/test_filesystem_audio_store.py, test_thread_pool_runner.py
  persistence/test_ledger.py, test_ledger_properties.py, test_job_queue.py, test_schema.py (extended)
  budget/test_meter.py, test_compose.py, test_no_unmetered_sdk_imports.py
  app/test_run_job.py, test_upload_recording.py
  api/test_recording_api.py, test_job_api.py, test_restart.py
  test_cli_upload.py
apps/web/src/shared/api/openapi.json, schema.d.ts   regenerated (Tasks 8 and 9)
```

## Task protocol (every task)

Each task starts with `git fetch origin && git switch -c p0c/NN-<slug> origin/main` and ends with: run `uv run pytest -q`, `uv run ruff check`, `uv run ruff format --check`, `uv run pyright` from `apps/api` (all clean); update `docs/superpowers/HANDOFF.md`; commit; `git push -u origin <branch>`; open a PR; when CI is green and review is done, `gh pr merge --squash` (no `--delete-branch`). Commit after each green TDD cycle, not only at the end. The last step of each task below says only "Finish the task" and means this protocol.

---

### Task 1: Pure WAV parsing, validation and resampling

**Branch:** `p0c/01-audio-domain`

**Files:**
- Create: `apps/api/src/nosolear/domain/errors.py`, `apps/api/src/nosolear/domain/audio.py`
- Modify: `apps/api/pyproject.toml` (add `numpy==<the version already in uv.lock>` as a direct dependency; run `uv lock`)
- Test: `apps/api/tests/domain/test_audio.py`, `apps/api/tests/domain/test_audio_properties.py`, `apps/api/tests/domain/test_errors.py`, `apps/api/tests/wavs.py` (create with the WAV builders)

**Interfaces:**
- **Consumes:** nothing. Salvage source: `git show p0b/spikes:spikes/common.py` (`_lowpass_kernel`, `_fft_filter`, `resample_to_16k`, `write_wav16k`).
- **Produces** (`nosolear.domain.errors`, the one module for every typed error the job runner and the API map):
  - `class NosolearError(ValueError)` with class attributes `code: ClassVar[str]` and `default_message: ClassVar[str]`, constructor `__init__(self, message: str | None = None)`, and property `safe_message -> str` (the given message, else `default_message`); `str(e) == e.safe_message`. A message is always a literal sentence written in Nosolear's code (for example "Azure Speech rejected the key or region; check NOSOLEAR_AZURE_SPEECH_KEY and NOSOLEAR_AZURE_SPEECH_REGION"), never built from provider text or a key.
  - `class InvalidAudio(NosolearError)`: `code = "invalid_audio"`, constructor `InvalidAudio(reason: AudioReason)` where `AudioReason = Literal["too_large", "too_long", "empty", "not_wav", "bad_chunks", "unsupported_format", "bad_sample_rate", "bad_content_type"]`; attribute `reason`.
  - `class CapExceeded(NosolearError)`: `code = "cap_exceeded"`; `class ProviderUnavailable(NosolearError)`: `code = "provider_unavailable"`; `class CapabilityMissing(NosolearError)`: `code = "capability_missing"`. Each has a fixed default message, so it can be raised with no argument.
  - `class RequestNotSent(ProviderUnavailable)`: raised by a raw adapter when it fails before any request left the machine (missing key or region, bad local input). The meter releases its reservation; the job shows `provider_unavailable` with the adapter's message naming the setting to fix. 0d adds `RetryableProviderError` and `MalformedProviderResponse` (both `ProviderUnavailable` subclasses) to this module, because domain parsers raise them.
  - `tests/domain/test_errors.py`: default and given messages, `str(e) == e.safe_message`, `RequestNotSent` is a `ProviderUnavailable` with code `provider_unavailable`.
- **Produces** (`nosolear.domain.audio`):
  - `TARGET_RATE = 16_000`; `ALLOWED_SAMPLE_RATES: frozenset[int] = frozenset({16000, 22050, 24000, 32000, 44100, 48000})`.
  - `@dataclass(frozen=True, slots=True) class AudioLimits: max_bytes: int = 10 * 1024 * 1024; max_duration_s: int = 120`; `DEFAULT_LIMITS = AudioLimits()`.
  - `@dataclass(frozen=True, slots=True) class WavAudio: sample_rate: int; samples: np.ndarray` (int16, mono, 1-D).
  - `check_declared_length(content_length: str | None, limits: AudioLimits = DEFAULT_LIMITS) -> None`: `None` passes; a non-integer or negative value or a value over `max_bytes` raises `InvalidAudio("too_large")` for over-cap and `InvalidAudio("not_wav")` for malformed.
  - `parse_wav(data: bytes, limits: AudioLimits = DEFAULT_LIMITS) -> WavAudio`.
  - `resample_to_16k(samples: np.ndarray, rate: int) -> np.ndarray` (float64 in, float64 out).
  - `to_16k(audio: WavAudio) -> np.ndarray` (int16 at 16 kHz).
  - `encode_wav(samples: np.ndarray, rate: int = TARGET_RATE) -> bytes` (canonical 44-byte header, 16-bit PCM mono).
  - `duration_ms(frames: int, rate: int) -> int` (rounded down).

- [ ] **Step 1: Write the failing example tests** in `tests/domain/test_audio.py`, with builders in `tests/wavs.py` (the one synthetic WAV factory; 0d adds `write_wav` and `wav_info` to it): `make_wav(seconds: float, rate: int = 16000, freq: float | None = 440.0) -> bytes` (a sine, or silence when `freq` is `None`; the header is built by hand with `struct` so any rate works) and `raw_wav(*, rate: int, pcm: bytes, declared_data: int | None = None, riff_size: int | None = None, extra_chunks: bytes = b"", fmt_tag: int = 1, channels: int = 1, bits: int = 16) -> bytes` so tests can make lying or malformed headers. Tests (names and key assertions):
  - `test_parses_valid_wav`: 1 s at 16 kHz gives `sample_rate == 16000`, `len(samples) == 16000`.
  - `test_duration_uses_frames_received`: header declares 100 s of data, body holds 2 s: `len(samples) == 2 * rate`. Same with `declared_data=0xFFFFFFFF`.
  - `test_declared_smaller_than_file_ignores_trailing_junk_chunk`: a `LIST` chunk after `data` is skipped; trailing bytes shorter than a chunk header are ignored.
  - `test_rejects_second_data_chunk_and_second_fmt_chunk` (`bad_chunks`), `test_rejects_missing_fmt_or_data` (`bad_chunks`).
  - `test_rejects_non_pcm16_mono`: `fmt_tag=3` (float), `fmt_tag=0xFFFE` (extensible), `bits=8`, `bits=24`, `channels=2` each raise `InvalidAudio("unsupported_format")`.
  - `test_rate_zero_is_invalid_audio`: rate 0 raises `InvalidAudio("bad_sample_rate")`, and so do 1, 8000 and 96000.
  - `test_rejects_over_duration_cap`: 121 s at 16 kHz raises `too_long`; exactly 120 s passes.
  - `test_rejects_empty_and_garbage`: `b""`, `b"RIFF"`, `b"not a wav"`, a RIFF whose form type is not `WAVE`, and zero frames (`empty`).
  - `test_odd_trailing_byte_dropped`: 2 s of PCM plus one stray byte gives `2 * rate` frames.
  - `test_check_declared_length`: `None` passes; `"10485760"` passes; `"10485761"` raises `too_large`; `"abc"`, `"-1"` raise `not_wav`.
  - `test_encode_wav_round_trips`: `parse_wav(encode_wav(x)).samples == x` for a fixed array.
  - `test_resample_length_and_tone`: 1 s of 440 Hz at each whitelisted rate resamples to 16000 ± 1 samples with RMS within 10% of the input RMS; a 10 kHz tone at 48 kHz is attenuated by at least 20 dB (anti-alias filter works).

- [ ] **Step 2: Run to verify failure.** Run: `uv run pytest tests/domain/test_audio.py -q`. Expected: FAIL with `ModuleNotFoundError: nosolear.domain.audio`.

- [ ] **Step 3: Implement `errors.py` and `audio.py`.**
  - `parse_wav` walks chunks with `struct`: require `RIFF`…`WAVE`; ignore the RIFF size field; for each chunk read id and declared size; `fmt ` must be 16 or more bytes with tag 1, 1 channel, 16 bits, rate in the whitelist (checked after reading it, so rate 0 is `bad_sample_rate`, not `unsupported_format`); `data` payload is `data[start : start + min(declared, remaining)]`; chunks are word-aligned (odd sizes pad one byte). A repeated `fmt ` or `data` is `bad_chunks`. Frames = `len(payload) // 2` (odd byte dropped). Duration check uses frames received: `frames > max_duration_s * rate` is `too_long`. Zero frames is `empty`. The input is also refused up front if `len(data) > limits.max_bytes` (`too_large`).
  - Samples come from `np.frombuffer(payload[:frames*2], dtype="<i2")` copied to native int16.
  - `resample_to_16k`: port from `common.py` (low-pass kernel at 7.6 kHz, FFT zero-phase filter, integer decimation when `rate % 16000 == 0`, else linear interpolation). Fixes: raise `InvalidAudio("bad_sample_rate")` for any `rate` not in `ALLOWED_SAMPLE_RATES`; return an empty array for empty input before touching the FFT. Drop the `soundfile` dependency: `encode_wav` writes the header with `struct` and the clipped, rounded int16 data.
  - `to_16k` converts int16 to float in [-1, 1), resamples, clips, rounds back to int16.

- [ ] **Step 4: Run to verify pass.** Run: `uv run pytest tests/domain/test_audio.py -q`. Expected: PASS.

- [ ] **Step 5: Write the Hypothesis properties** in `tests/domain/test_audio_properties.py` (strategies build headers from `tests/wavs.py::raw_wav`):
  - `test_parse_never_raises_anything_but_invalid_audio`: arbitrary `bytes` (and arbitrary bytes after a valid RIFF/WAVE prefix) either parse or raise `InvalidAudio`; no other exception type.
  - `test_header_lies_never_crash`: valid PCM with arbitrary `declared_data` (0 to 2**32-1), arbitrary `riff_size`, and arbitrary rate (0 to 200000): result is a `WavAudio` whose frame count equals `min(declared, actual) // 2` when the rate is whitelisted, else `InvalidAudio`.
  - `test_frames_never_exceed_bytes_received`: `len(samples) <= len(data) // 2` always.
  - `test_resample_length_is_proportional`: for whitelisted rates and 0 to 20000 input samples, `abs(len(out) - len(x) * 16000 / rate) <= 1`.
  - `test_to_16k_stays_in_int16_range_and_encodes`: `parse_wav(encode_wav(to_16k(audio)))` succeeds with the same length.
  - `test_encode_parse_round_trip`: arbitrary int16 arrays up to 5000 samples round-trip exactly.

- [ ] **Step 6: Run to verify pass.** Run: `uv run pytest tests/domain -q` and also `HYPOTHESIS_PROFILE=heavy uv run pytest tests/domain/test_audio_properties.py -q`. Expected: PASS. Fix the implementation, not the properties, if a counterexample appears.

- [ ] **Step 7: Finish the task** (protocol above). Commit message: "Add pure WAV parsing, validation and resampling".

---

### Task 2: AudioStore port, filesystem adapter and fake

**Branch:** `p0c/02-audio-store`

**Files:**
- Create: `apps/api/src/nosolear/ports/audio.py`, `apps/api/src/nosolear/adapters/filesystem_audio_store.py`
- Modify: `apps/api/tests/fakes.py` (add `FakeAudioStore`)
- Test: `apps/api/tests/adapters/test_filesystem_audio_store.py`, `apps/api/tests/test_audio_store_contract.py`

**Interfaces:**
- **Consumes:** Task 1 (`parse_wav`, `to_16k`, `encode_wav`, `duration_ms`, `AudioLimits`, `InvalidAudio`).
- **Produces** (`nosolear.ports.audio`):
  ```python
  @dataclass(frozen=True, slots=True)
  class StoredRecording:
      path: str          # always "recordings/<uuid>.wav", relative to the data dir
      duration_ms: int
      sample_rate: int   # always 16000
      sha256: str        # hex digest of the stored file

  @dataclass(frozen=True, slots=True)
  class Recording:       # a row of the recordings table
      id: str
      attempt_id: str
      path: str
      duration_ms: int
      sample_rate: int
      sha256: str

  class PendingUpload(Protocol):
      def write(self, chunk: bytes) -> None: ...   # raises InvalidAudio("too_large") once the cap is passed; the upload is then aborted
      def commit(self) -> StoredRecording: ...     # validate, resample, store; raises InvalidAudio; temp file always removed
      def abort(self) -> None: ...                 # idempotent

  class AudioStore(Protocol):
      def begin_upload(self) -> PendingUpload: ...
      def read(self, path: str) -> bytes: ...
      def resolve(self, path: str) -> Path: ...    # absolute path for libraries that need a file; raises ValueError if not a stored recording path
      def delete(self, path: str) -> None: ...
  ```
- **Produces** (`nosolear.adapters.filesystem_audio_store`): `FilesystemAudioStore(data_dir: Path, *, limits: AudioLimits = DEFAULT_LIMITS)`.
- **Produces** (`tests/fakes.py`): `FakeAudioStore(limits: AudioLimits = DEFAULT_LIMITS)`, in-memory, runs the same domain validation, records paths as `recordings/<uuid4>.wav`, exposes `files: dict[str, bytes]`.

- [ ] **Step 1: Write the failing tests** in `tests/adapters/test_filesystem_audio_store.py` (use `tmp_path`):
  - `test_commit_stores_16k_under_generated_name`: upload a 48 kHz WAV in several chunks; `path` matches `^recordings/[0-9a-f-]{36}\.wav$`, the file exists under `tmp_path`, parses as 16 kHz mono, `duration_ms` matches, `sha256` equals the file's hash, `sample_rate == 16000`.
  - `test_permissions`: the file mode is `0o600`, the `recordings` dir `0o700`.
  - `test_temp_file_is_inside_data_dir_and_removed`: during an upload exactly one file exists under `recordings/.incoming/`; after `commit` or `abort` the directory is empty; nothing is written outside `tmp_path` (monkeypatch `tempfile.gettempdir` to raise to prove it is never used).
  - `test_write_past_cap_aborts` (Review Focus 3): with `AudioLimits(max_bytes=1000)`, writing 600 + 600 bytes raises `InvalidAudio("too_large")` on the second write, and `.incoming` is empty afterwards.
  - `test_commit_invalid_audio_leaves_nothing`: garbage bytes raise `InvalidAudio("not_wav")` and leave no file in `recordings/` or `.incoming/`.
  - `test_two_commits_get_distinct_names`.
  - `test_resolve_refuses_paths_outside_recordings` (parametrized): `"../x.wav"`, `"/etc/passwd"`, `"recordings/../../x.wav"`, `"recordings/a.wav"`, `"recordings/" + "0"*36 + ".mp3"`, `"recordings/.incoming/x"`, an existing symlink inside `recordings/` pointing outside the data dir: each raises `ValueError`; `read` and `delete` refuse the same inputs.
  - `test_startup_sweeps_stale_incoming_files`: a leftover `.incoming/x.part` is removed when a new `FilesystemAudioStore` is constructed.
  - `test_delete_removes_file_and_is_idempotent`.
  - In `tests/test_audio_store_contract.py`, a parametrized fixture over `FilesystemAudioStore` and `FakeAudioStore` runs the shared behaviours: valid commit, over-cap write, invalid audio, `read` returns the stored bytes, `delete`.

- [ ] **Step 2: Run to verify failure.** Run: `uv run pytest tests/adapters/test_filesystem_audio_store.py tests/test_audio_store_contract.py -q`. Expected: FAIL (modules missing).

- [ ] **Step 3: Implement the port, adapter and fake.**
  - `FilesystemAudioStore.__init__` creates `recordings/` (0700) and `recordings/.incoming/` and sweeps stale `.incoming` files.
  - `begin_upload` opens `.incoming/<uuid4>.part` with `os.open(..., O_WRONLY|O_CREAT|O_EXCL, 0o600)`; the pending object counts bytes and raises past `limits.max_bytes` (after aborting).
  - `commit`: close the temp file, read it (at most 10 MB), `parse_wav`, `to_16k`, `encode_wav`, write `recordings/<uuid4>.wav` with `O_EXCL` and mode 0600, compute sha256, delete the temp file in a `finally`.
  - `resolve`: accept only strings matching `^recordings/[0-9a-f-]{36}\.wav$`, then `Path.resolve()` and require `is_relative_to(data_dir.resolve() / "recordings")` (this catches symlinks).
  - The fake shares the same validation by calling the domain functions on the joined chunks.

- [ ] **Step 4: Run to verify pass.** Run: `uv run pytest tests/adapters tests/test_audio_store_contract.py -q`. Expected: PASS.

- [ ] **Step 5: Finish the task.** Commit message: "Add AudioStore port with filesystem adapter and fake".

---

### Task 3: Schema for recordings, jobs, usage ledger and analyses

**Branch:** `p0c/03-schema`

**Files:**
- Create: `apps/api/src/nosolear/persistence/migrations/versions/0004_recordings_jobs_ledger.py`
- Modify: `apps/api/src/nosolear/persistence/models.py`, `apps/api/src/nosolear/persistence/db.py`
- Test: `apps/api/tests/persistence/test_schema.py` (extend), `apps/api/tests/persistence/test_db.py` (extend)

**Interfaces:**
- **Consumes:** existing `metadata`, `UTCDateTime`, `_in_list`; 0b's migration `0003` is the head (`down_revision = "0003"`; confirm with `uv run alembic heads` after rebasing on `origin/main`).
- **Produces:** tables per ARCHITECTURE.md §7, as SQLAlchemy Core `Table`s in `models.py`:
  - `recordings(id TEXT pk, attempt_id TEXT NOT NULL UNIQUE FK attempts.id, path TEXT NOT NULL UNIQUE, duration_ms INTEGER NOT NULL, sample_rate INTEGER NOT NULL, sha256 TEXT NOT NULL, created_at)`; CHECK `path GLOB 'recordings/*.wav'`, `duration_ms >= 0`, `sample_rate = 16000`.
  - `jobs(id TEXT pk, kind, attempt_id TEXT NULL FK attempts.id, status, step TEXT NULL, progress REAL NOT NULL, steps_json TEXT NOT NULL, tries INTEGER NOT NULL, created_at, updated_at)`; CHECKs `kind IN ('analyze','rescore')`, `status IN ('queued','running','done','failed')`, `progress BETWEEN 0 AND 1`, `tries >= 0`; index `ix_jobs_status_created (status, created_at)`.
  - `usage_ledger(id INTEGER pk autoincrement, provider, unit, state, estimate INTEGER NOT NULL, actual INTEGER NULL, period TEXT NOT NULL, job_id TEXT NULL FK jobs.id, created_at, settled_at NULL)`; CHECKs `provider IN ('azure','anthropic')`, `unit IN ('audio_seconds','tts_chars','tokens')`, `state IN ('reserved','recorded','released')`, `estimate >= 0`, `(state = 'recorded') = (actual IS NOT NULL)`; index `ix_ledger_totals (provider, unit, period, state)`. Quantities are integers: audio seconds are rounded up to whole seconds, so estimates stay upper bounds and sums are exact.
  - `analyses(id INTEGER pk autoincrement, attempt_id NULL FK attempts.id, tts_hash NULL, calibration_run_id NULL, kind, provider, provider_version, adapter, adapter_version INTEGER, raw_json TEXT NOT NULL, created_at)`; CHECK `kind IN ('pronunciation','transcript','phone_probe','coach')`; CHECK exactly one key shape: `(attempt_id IS NOT NULL AND tts_hash IS NULL AND calibration_run_id IS NULL) OR (attempt_id IS NULL AND tts_hash IS NOT NULL AND calibration_run_id IS NOT NULL)`; partial unique index on `(attempt_id, kind) WHERE attempt_id IS NOT NULL` and on `(tts_hash, kind, calibration_run_id) WHERE attempt_id IS NULL`. `tts_hash` and `calibration_run_id` have no foreign keys yet; 0e's migration adds them when `calibration_runs` exists (0d creates `tts_cache`). This table is complete for 0e's control rows: 0e adds only the two foreign keys.
  - `_set_pragmas` also runs `PRAGMA busy_timeout=5000`.

- [ ] **Step 1: Write the failing tests** extending `test_schema.py` (keep its `test_models_match_migrations` drift guard; it fails until models and migration agree) and the CHECK style already used there:
  - `test_recordings_unique_per_attempt_and_path_shape`: a second row for the same attempt, a `path` of `../x.wav`, and a `sample_rate` of 48000 each raise `IntegrityError`.
  - `test_jobs_checks`: bad `kind`, bad `status`, `progress` of 1.5 each raise `IntegrityError`; a rescore job with `attempt_id` NULL is accepted.
  - `test_ledger_checks`: bad provider, bad unit, bad state, a `recorded` row with `actual` NULL, a `reserved` row with `actual` set each raise; `job_id` NULL is accepted.
  - `test_analyses_exactly_one_key_shape`: a row with both `attempt_id` and `tts_hash`, a row with neither, and a TTS row missing `calibration_run_id` raise; a duplicate `(attempt_id, kind)` raises; two TTS rows with the same hash and kind but different runs are accepted.
  - In `test_db.py`: `test_busy_timeout_is_set` (`PRAGMA busy_timeout` returns 5000 on a fresh connection).
  - `test_migration_downgrade_then_upgrade` (the 0004 downgrade drops all four tables and upgrade restores them).

- [ ] **Step 2: Run to verify failure.** Run: `uv run pytest tests/persistence -q`. Expected: FAIL (tables missing).

- [ ] **Step 3: Implement the tables in `models.py`, the migration `0004_recordings_jobs_ledger.py` (explicit `op.create_table` calls with the same CHECK names as the models, e.g. `ck_jobs_status`; partial indexes via `sqlite_where`), and the pragma.**

- [ ] **Step 4: Run to verify pass.** Run: `uv run pytest tests/persistence -q`. Expected: PASS, including the drift guard.

- [ ] **Step 5: Finish the task.** Commit message: "Add recordings, jobs, usage ledger and analyses tables".

---

### Task 4: Usage ledger

**Branch:** `p0c/04-usage-ledger`

**Files:**
- Create: `apps/api/src/nosolear/domain/budget.py`, `apps/api/src/nosolear/ports/ledger.py`, `apps/api/src/nosolear/persistence/ledger.py`
- Modify: `apps/api/tests/fakes.py` (add `FakeUsageLedger`)
- Test: `apps/api/tests/domain/test_budget.py`, `apps/api/tests/persistence/test_ledger.py`, `apps/api/tests/persistence/test_ledger_properties.py`

**Interfaces:**
- **Consumes:** Task 3 `usage_ledger` table; `Clock` port; `CapExceeded` (Task 1).
- **Produces** (`nosolear.domain.budget`):
  ```python
  class Provider(StrEnum): AZURE = "azure"; ANTHROPIC = "anthropic"
  class Unit(StrEnum): AUDIO_SECONDS = "audio_seconds"; TTS_CHARS = "tts_chars"; TOKENS = "tokens"

  @dataclass(frozen=True, slots=True)
  class Caps:
      azure_audio_seconds: int     # monthly
      azure_tts_chars: int         # monthly
      claude_tokens: int           # daily
      @classmethod
      def from_hours_chars_tokens(cls, *, azure_audio_hours: float, azure_tts_chars: int, claude_tokens: int) -> "Caps"  # hours * 3600, floored
      def limit(self, provider: Provider, unit: Unit) -> int   # ValueError for an unsupported pair

  DEFAULT_CAPS = Caps.from_hours_chars_tokens(azure_audio_hours=4.5, azure_tts_chars=450_000, claude_tokens=100_000)
  def period_for(provider: Provider, unit: Unit, now: datetime) -> str       # azure: "YYYY-MM", anthropic: "YYYY-MM-DD", in UTC; naive datetimes raise ValueError
  def fits(cap: int, recorded: int, reserved: int, estimate: int) -> bool    # recorded + reserved + estimate <= cap
  def ceil_seconds(seconds: float) -> int                                    # rounds up, never below 0
  @dataclass(frozen=True, slots=True)
  class Usage: provider: Provider; unit: Unit; period: str; recorded: int; reserved: int; cap: int
  ```
- **Produces** (`nosolear.ports.ledger`):
  ```python
  @dataclass(frozen=True, slots=True)
  class Reservation: id: int; provider: Provider; unit: Unit; estimate: int; period: str

  class UsageLedger(Protocol):
      def reserve(self, provider: Provider, unit: Unit, estimate: int, *, job_id: str | None = None) -> Reservation  # raises CapExceeded
      def record(self, reservation: Reservation, actual: int) -> None      # open reservation only; else LedgerError
      def release(self, reservation: Reservation) -> None                  # open reservation only; else LedgerError
      def settle_open_reservations(self) -> int                            # startup: every open reservation becomes recorded at its estimate; returns the count
      def usage(self, provider: Provider, unit: Unit) -> Usage             # for the current period
  ```
  and `class LedgerError(ValueError)` in the same module.
- **Produces** (`nosolear.persistence.ledger`): `SqliteUsageLedger(engine: Engine, *, caps: Caps, clock: Clock)`.
- **Produces** (`tests/fakes.py`): `FakeUsageLedger(caps: Caps, clock: Clock)` using the same `fits` and `period_for` arithmetic in memory.

- [ ] **Step 1: Write the failing domain tests** (`test_budget.py`): `test_default_caps` (`DEFAULT_CAPS.azure_audio_seconds == 16200`, `azure_tts_chars == 450000`, `claude_tokens == 100000`); `test_period_for` (Azure `2026-11-30T23:59:59Z` is `"2026-11"`; Claude is `"2026-11-30"`; an input at `+05:45` is converted to UTC first: `2026-12-01T03:00+05:45` gives Azure `"2026-11"`); `test_naive_datetime_rejected`; `test_limit_rejects_unsupported_pair` (`(ANTHROPIC, AUDIO_SECONDS)`); `test_fits_boundary` (exactly at the cap fits, one over does not); `test_ceil_seconds` (`0.0 -> 0`, `0.01 -> 1`, `3.0 -> 3`, negative -> 0). Property: `test_fits_is_monotone_in_estimate` (if `fits` for estimate e, it fits for any smaller non-negative e).

- [ ] **Step 2: Run to verify failure.** Run: `uv run pytest tests/domain/test_budget.py -q`. Expected: FAIL (module missing).

- [ ] **Step 3: Implement `domain/budget.py` and `ports/ledger.py`.** Run the domain tests: PASS.

- [ ] **Step 4: Write the failing adapter tests** (`test_ledger.py`, file-backed engine from the `db_engine` fixture, `FixedClock` from `factories`):
  - `test_reserve_record_flow`: reserve 100 tokens then record 80; `usage(...)` shows `recorded == 80, reserved == 0`.
  - `test_reserve_over_cap_raises_and_writes_nothing`: cap 100, reserve 101 raises `CapExceeded`; the table is empty.
  - `test_open_reservations_count_against_cap`: cap 100, reserve 60, then reserve 41 raises, reserve 40 passes.
  - `test_release_frees_headroom`; `test_double_settle_is_ledger_error` (record twice, release after record, record after release).
  - `test_orphans_settle_at_estimate` (Review Focus 4): reserve 50 without settling, build a new `SqliteUsageLedger` on the same engine, `settle_open_reservations() == 1`, usage shows `recorded == 50`, and the row is `recorded` with `actual == 50` (not `released`).
  - `test_period_rolls_over`: with a clock moved to the next UTC day, Claude usage starts again from 0 while the earlier day's rows stay; Azure rolls on the month.
  - `test_job_id_is_optional_and_stored`.
  - `test_reserve_takes_write_lock_before_reading`: open a second connection holding `BEGIN IMMEDIATE`; with `busy_timeout` lowered to 50 ms on the ledger engine, `reserve` raises `OperationalError` ("database is locked") rather than reading stale totals.
  - `test_threads_cannot_overspend` (Review Focus 5): 8 threads each reserve 30 against a cap of 100 behind a `threading.Barrier`; exactly 3 succeed, 5 get `CapExceeded`, and `usage().reserved == 90`.

- [ ] **Step 5: Run to verify failure, then implement `SqliteUsageLedger`.** Approach: each operation opens `engine.connect()`, executes `conn.exec_driver_sql("BEGIN IMMEDIATE")` first (pysqlite's legacy transaction mode does not begin a second transaction, so this takes the write lock before the totals are read), computes totals with `SUM` over `recorded.actual` and `reserved.estimate` for `(provider, unit, period)`, applies `fits`, inserts, and `conn.commit()`; roll back on any exception. `record` and `release` update `WHERE id = :id AND state = 'reserved'` and raise `LedgerError` when `rowcount == 0`. `settle_open_reservations` is one `UPDATE ... SET state='recorded', actual=estimate, settled_at=:now WHERE state='reserved'`. Run: `uv run pytest tests/persistence/test_ledger.py -q`. Expected: PASS. If `test_reserve_takes_write_lock_before_reading` shows the lock is not taken, fix the transaction handling, not the test.

- [ ] **Step 6: Write the stateful property** in `test_ledger_properties.py` (use `tempfile.TemporaryDirectory` inside the machine, not `tmp_path`, to avoid Hypothesis function-scoped fixture warnings). `class LedgerMachine(RuleBasedStateMachine)` on a fresh `SqliteUsageLedger` with `Caps(azure_audio_seconds=100, azure_tts_chars=100, claude_tokens=100)`:
  - rule `reserve(unit, estimate in 0..60)`: on success append to `open`; on `CapExceeded` assert `usage.recorded + usage.reserved + estimate > cap` for that unit.
  - rule `record` (pick an open reservation; `actual` in `0..estimate`, since estimates are upper bounds), rule `release`, rule `crash_and_restart` (new ledger object on the same engine, `settle_open_reservations`, clear `open`).
  - invariant, checked for all three units after every step: `usage.recorded + usage.reserved <= usage.cap`.
  - A second invariant compares `usage()` with a plain-Python model that applies the same operations.
  Also `test_fake_ledger_matches_sqlite_ledger`: the same random operation sequence gives identical outcomes (pass or `CapExceeded`) and totals on `FakeUsageLedger` and `SqliteUsageLedger`.
  Run: `uv run pytest tests/persistence/test_ledger_properties.py -q` and with `HYPOTHESIS_PROFILE=heavy`. Expected: PASS.

- [ ] **Step 7: Finish the task.** Commit message: "Add usage ledger with cap reservations".

---

### Task 5: Metered decorator and paid-port composition

**Branch:** `p0c/05-meter-composition`

**Files:**
- Create: `apps/api/src/nosolear/budget/__init__.py`, `apps/api/src/nosolear/budget/meter.py`, `apps/api/src/nosolear/budget/compose.py`
- Modify: `apps/api/src/nosolear/api/deps.py` (add `build_paid_ports`), `apps/api/tests/fakes.py` (add `FakePaidPort`)
- Test: `apps/api/tests/budget/test_meter.py`, `apps/api/tests/budget/test_compose.py`, `apps/api/tests/budget/test_no_unmetered_sdk_imports.py`, `apps/api/tests/api/test_deps_composition.py`

**Interfaces:**
- **Consumes:** Task 4 (`UsageLedger`, `Reservation`, `Provider`, `Unit`, `FakeUsageLedger`, `SqliteUsageLedger`); `CapExceeded`, `RequestNotSent` (Task 1).
- **Produces** (`nosolear.budget.meter`):
  ```python
  class Meter:
      def __init__(self, ledger: UsageLedger, *, job_id: Callable[[], str | None] = lambda: None) -> None
      def call[R](self, provider: Provider, unit: Unit, estimate: int, fn: Callable[[], R], actual: Callable[[R], int]) -> R

  def metered_method[**P, R](meter: Meter, *, provider: Provider, unit: Unit,
                             estimate: Callable[P, int], actual: Callable[[R], int]) -> Callable[[Callable[P, R]], Callable[P, R]]
  ```
  `Meter.call` semantics: `ledger.reserve(...)` with `job_id=self.job_id()` (propagates `CapExceeded`, `fn` is never called); then `fn()`; success records `actual(result)`; `RequestNotSent` releases and re-raises; any other exception records at the estimate and re-raises. `metered_method` wraps one bound method so a port wrapper written in Phase 0d is a few lines per method. The composition root builds `Meter(ledger, job_id=current_job_id)` (Task 7), so every reservation made inside a job carries its id.
- **Produces** (`nosolear.budget.compose`):
  ```python
  class PortWrapper[T]:
      layer: ClassVar[str]          # "cache" | "retry" | "metered" | "raw"
      inner: T

  def compose_paid_port[T](raw: T, *, metered: Callable[[T], T], retry: Callable[[T], T],
                           cache: Callable[[T], T] | None = None) -> T   # returns cache(retry(metered(raw)))
  def layers_of(port: object) -> list[str]   # outermost first, following `.inner`; the last item is the raw adapter's own `layer` ("raw")
  ```
- **Produces** (`api/deps.py`): `build_paid_ports(settings: Settings, *, ledger: UsageLedger, clock: Clock) -> dict[str, object]`, returning `{}` in this phase. Phase 0d replaces it with `build_providers(...) -> Providers`, whose `paid_ports()` returns the same dict (`pronunciation_scorer`, `transcriber_azure`, `synthesizer`, `coach`, each built only through `compose_paid_port`), and points `test_deps_composition.py` at that.
- **Produces** (`tests/fakes.py`): `FakePaidPort` with `layer = "raw"`, `calls: int`, `def run(self, units: int) -> int` (returns `units`) and a `fail_with: Exception | None`.

- [ ] **Step 1: Write the failing tests** (`test_meter.py`, with `FakeUsageLedger` and `FakePaidPort`):
  - `test_success_records_actual`: estimate 100, actual 70: `usage.recorded == 70`, `reserved == 0`.
  - `test_cap_exceeded_makes_no_call`: cap 50, estimate 100: `CapExceeded` and `port.calls == 0` (the done-when sentence "refused without being made").
  - `test_request_not_sent_releases`: `fail_with=RequestNotSent()`: re-raised, `usage.recorded == 0 and reserved == 0`.
  - `test_other_failure_records_estimate`: `fail_with=RuntimeError("boom")`: re-raised, `usage.recorded == estimate`.
  - `test_metered_method_wraps_signature`: the decorated function keeps its arguments, uses `estimate(*args, **kwargs)` for the estimate, and the job id from the `job_id` callable is stored on the ledger row (check with the SQLite ledger).
  - `test_each_retry_attempt_reserves_on_its_own`: a retry wrapper (test double, `layer = "retry"`) that calls a failing metered inner twice then succeeds yields three ledger rows (two recorded at the estimate, one at actual).
- `test_compose.py`: `test_compose_order_is_cache_retry_metered_raw` builds recording wrappers (subclasses of `PortWrapper` with the four layer names) and asserts `layers_of(compose_paid_port(raw, metered=..., retry=..., cache=...)) == ["cache", "retry", "metered", "raw"]`; `test_without_cache_order_is_retry_metered_raw`; `test_layers_of_raw_only`.
- `test_deps_composition.py`: `test_every_paid_port_the_composition_root_builds_is_ordered`: iterates `build_paid_ports(...)` and, for each port, asserts `layers_of(port)` ends with `["retry", "metered", "raw"]`, has `"cache"` only as the outermost layer and only for the key `synthesizer`, and that no port is a bare raw adapter. It is vacuous in this phase (empty dict); add `test_the_check_has_teeth` which feeds a deliberately mis-ordered stack (metered outside retry) and a bare raw port into the same assertion helper and expects each to fail. Phase 0d must keep this test non-vacuous.
- `test_no_unmetered_sdk_imports.py`: AST-scans every `.py` under `src/nosolear` for imports whose top-level module is in `{"azure", "anthropic", "faster_whisper", "mlx_whisper", "mlx", "torch", "transformers", "huggingface_hub", "parselmouth"}` and asserts the importing file is in `RAW_ADAPTER_MODULES: frozenset[str]` (empty now; 0d turns it into a module → allowed-SDKs mapping and adds a lazy-import rule, in this same file). A second test plants a fake offending file in `tmp_path` to show the scanner flags it.

- [ ] **Step 2: Run to verify failure.** Run: `uv run pytest tests/budget tests/api/test_deps_composition.py -q`. Expected: FAIL (modules missing).

- [ ] **Step 3: Implement `meter.py`, `compose.py`, `build_paid_ports`, `FakePaidPort`.**

- [ ] **Step 4: Run to verify pass.** Run: `uv run pytest tests/budget tests/api -q`. Expected: PASS.

- [ ] **Step 5: Finish the task.** Commit message: "Add metered decorator and paid-port composition order".

---

### Task 6: Job domain and SQLite job queue

**Branch:** `p0c/06-job-queue`

**Files:**
- Create: `apps/api/src/nosolear/domain/jobs.py`, `apps/api/src/nosolear/ports/jobs.py`, `apps/api/src/nosolear/persistence/job_queue.py`
- Modify: `apps/api/tests/fakes.py` (add `FakeJobQueue`)
- Test: `apps/api/tests/domain/test_jobs.py`, `apps/api/tests/domain/test_jobs_properties.py`, `apps/api/tests/persistence/test_job_queue.py`

**Interfaces:**
- **Consumes:** Task 3 `jobs` table; `Clock`.
- **Produces** (`nosolear.domain.jobs`):
  ```python
  class JobKind(StrEnum): ANALYZE = "analyze"; RESCORE = "rescore"
  class JobStatus(StrEnum): QUEUED = "queued"; RUNNING = "running"; DONE = "done"; FAILED = "failed"
  class StepState(StrEnum): PENDING = "pending"; RUNNING = "running"; DONE = "done"; SKIPPED = "skipped"; FAILED = "failed"; BLOCKED = "blocked"

  @dataclass(frozen=True, slots=True)
  class StepSpec:
      name: str
      needs: tuple[str, ...] = ()   # hard: needs that step's output; BLOCKED if it failed or is blocked
      uses: tuple[str, ...] = ()    # soft: runs regardless, but is re-run on resume if any of these re-ran

  JOB_PLANS: dict[JobKind, tuple[StepSpec, ...]] = {
      JobKind.ANALYZE: (StepSpec("score"), StepSpec("transcribe"), StepSpec("probe"),
                        StepSpec("coach", needs=("transcribe",)),
                        StepSpec("extract", uses=("score", "transcribe", "probe", "coach"))),
      JobKind.RESCORE: (StepSpec("extract"),),
  }

  @dataclass(frozen=True, slots=True)
  class StepRecord:
      name: str
      state: StepState = StepState.PENDING
      error_code: str | None = None     # NosolearError.code, or "internal_error"
      message: str | None = None        # safe message only; also used for skip reasons ("not_applicable", "not_available")

  @dataclass(frozen=True, slots=True)
  class Job:
      id: str; kind: JobKind; attempt_id: str | None; status: JobStatus
      step: str | None; progress: float; steps: tuple[StepRecord, ...]; tries: int
      created_at: datetime; updated_at: datetime

  def initial_steps(kind: JobKind) -> tuple[StepRecord, ...]
  def progress_of(steps: Sequence[StepRecord]) -> float      # share of steps in DONE, SKIPPED, FAILED or BLOCKED
  def final_status(steps: Sequence[StepRecord]) -> JobStatus # FAILED if any step is FAILED or BLOCKED, else DONE
  def resume_plan(kind: JobKind, steps: Sequence[StepRecord]) -> tuple[StepRecord, ...]
  def recover_running(steps: Sequence[StepRecord]) -> tuple[StepRecord, ...]   # RUNNING -> PENDING, errors cleared
  ```
  `resume_plan` resets every FAILED or BLOCKED step to PENDING, plus (walking the plan in order) every step whose `needs` or `uses` includes a reset step; DONE and SKIPPED steps outside that closure are untouched.
- **Produces** (`nosolear.ports.jobs`):
  ```python
  class JobQueue(Protocol):
      def enqueue(self, kind: JobKind, attempt_id: str | None) -> Job            # status QUEUED, steps from initial_steps
      def claim_next(self) -> Job | None                                          # atomically oldest QUEUED -> RUNNING, tries += 1
      def get(self, job_id: str) -> Job | None
      def update(self, job_id: str, *, steps: Sequence[StepRecord], step: str | None, progress: float, status: JobStatus | None = None) -> None
      def resume(self, job_id: str) -> Job                                        # FAILED -> QUEUED with resume_plan; ValueError (JobNotResumable) otherwise
      def requeue_running(self) -> int                                            # startup: RUNNING -> QUEUED with recover_running; returns the count
  ```
  plus `class JobNotResumable(ValueError)` and `class UnknownJob(ValueError)` in the same module. `SqliteJobQueue(engine: Engine, *, clock: Clock)` and `FakeJobQueue(clock)`; `steps_json` is `[{"name","state","error_code","message"}, ...]`.

- [ ] **Step 1: Write the failing domain tests** (`test_jobs.py`): `test_plans_match_architecture_order` (analyze steps are `score, transcribe, probe, coach, extract`; rescore is `extract`); `test_initial_steps_all_pending`; `test_progress_counts_settled_steps`; `test_final_status`; `test_resume_resets_failed_and_dependents`: coach failed and extract done gives coach and extract PENDING, others untouched; transcribe failed and coach blocked gives transcribe, coach, extract PENDING, score and probe untouched; `test_recover_running_resets_running_step_only`.
  Properties (`test_jobs_properties.py`, strategies draw an arbitrary state per step): `resume_plan` never changes a DONE or SKIPPED step that is not in the dependency closure of a reset step; after `resume_plan`, no step is FAILED or BLOCKED; `resume_plan` is idempotent; `recover_running` leaves no RUNNING step and never touches other states.

- [ ] **Step 2: Run to verify failure, implement `domain/jobs.py` and `ports/jobs.py`, run to verify pass.** Run: `uv run pytest tests/domain/test_jobs.py tests/domain/test_jobs_properties.py -q`.

- [ ] **Step 3: Write the failing queue tests** (`test_job_queue.py`, db fixture, `FixedClock`; the same assertions also run against `FakeJobQueue` through a parametrized fixture):
  - `test_enqueue_creates_queued_job_with_pending_steps`; `test_enqueue_rescore_has_no_attempt`.
  - `test_claim_next_is_fifo_and_marks_running`: two jobs claimed in creation order, `tries == 1`, a third claim returns `None`.
  - `test_two_threads_never_claim_the_same_job`: 20 queued jobs, 4 threads loop on `claim_next`; every job is claimed exactly once.
  - `test_update_persists_steps_progress_and_status` and `test_steps_json_holds_only_safe_fields`.
  - `test_requeue_running_resets_running_steps` (Review Focus 4): a job RUNNING with a RUNNING step and a DONE step comes back QUEUED with the RUNNING step PENDING and the DONE step intact; `tries` is kept; returns the count; FAILED and DONE jobs are untouched.
  - `test_resume_failed_job_requeues_with_reset_steps`; `test_resume_non_failed_job_raises_job_not_resumable`; `test_resume_unknown_job_raises_unknown_job`.
  - `test_get_unknown_returns_none`.

- [ ] **Step 4: Run to verify failure, implement `SqliteJobQueue` and `FakeJobQueue`, run to verify pass.** `claim_next` runs `BEGIN IMMEDIATE` (same technique as the ledger) so the select-and-update is atomic. Job ids are `uuid4().hex`. Run: `uv run pytest tests/persistence/test_job_queue.py -q`. Expected: PASS.

- [ ] **Step 5: Finish the task.** Commit message: "Add job domain model and SQLite job queue".

---

### Task 7: Step registry, run_job use case, analysis store

**Branch:** `p0c/07-run-job`

**Files:**
- Create: `apps/api/src/nosolear/domain/analyses.py`, `apps/api/src/nosolear/ports/analyses.py`, `apps/api/src/nosolear/app/steps.py`, `apps/api/src/nosolear/app/run_job.py`
- Modify: `apps/api/src/nosolear/persistence/repositories.py` (add `AnalysisRepository`), `apps/api/tests/fakes.py` (add `FakeAnalysisStore`, `FakeStep`)
- Test: `apps/api/tests/app/test_run_job.py`, `apps/api/tests/persistence/test_repositories.py` (extend)

**Interfaces:**
- **Consumes:** Task 6 (`Job`, `JobQueue`, `JOB_PLANS`, `StepRecord`, `StepState`, `final_status`, `progress_of`), Task 5 (`Meter`) for the cap test, Task 1 errors.
- **Produces** (`nosolear.domain.analyses`):
  ```python
  class AnalysisKind(StrEnum): PRONUNCIATION = "pronunciation"; TRANSCRIPT = "transcript"; PHONE_PROBE = "phone_probe"; COACH = "coach"

  @dataclass(frozen=True, slots=True)
  class NewAnalysis:
      attempt_id: str; kind: AnalysisKind; provider: str; provider_version: str
      adapter: str; adapter_version: int; raw: Mapping[str, object]

  @dataclass(frozen=True, slots=True)
  class StoredAnalysis:   # same fields as NewAnalysis plus id: int and created_at: datetime
  ```
- **Produces** (`nosolear.ports.analyses`):
  ```python
  class AnalysisStore(Protocol):
      def get(self, attempt_id: str, kind: AnalysisKind) -> StoredAnalysis | None
      def put(self, analysis: NewAnalysis) -> StoredAnalysis   # idempotent: returns the existing row if (attempt_id, kind) exists; never overwrites
      def for_attempt(self, attempt_id: str) -> list[StoredAnalysis]
  ```
  `AnalysisRepository(engine, clock)` and `FakeAnalysisStore`. Control rows keyed by TTS hash are Phase 0e's addition to this port; the table already supports them.
- **Produces** (`nosolear.app.steps`) — **the interface Phases 0d and 0e plug into:**
  ```python
  @dataclass(frozen=True, slots=True)
  class StepContext:
      job_id: str
      kind: JobKind
      attempt_id: str | None
      progress: Callable[[float], None]   # fraction 0..1 within this step; run_job persists
                                          # (settled steps + fraction) / len(plan). 0e's rescore and calibration use it.

  def current_job_id() -> str | None      # a ContextVar run_job sets around each step's run(); the Meter reads it

  class Step(Protocol):
      name: str                                    # one of the names in JOB_PLANS[kind]
      def applies(self, ctx: StepContext) -> bool  # False -> step is SKIPPED with message "not_applicable" (e.g. phone probe on free talk)
      def run(self, ctx: StepContext) -> None      # idempotent: first looks for its own stored analysis and returns without a provider call if present;
                                                   # raises a NosolearError subclass on failure; any other exception becomes "internal_error"

  class StepRegistry:
      def register(self, kind: JobKind, step: Step) -> None   # ValueError if step.name is not in JOB_PLANS[kind] or is already registered for the kind
      def get(self, kind: JobKind, name: str) -> Step | None
  ```
  Step conventions (for 0d/0e): a step builds its own dependencies at construction (ports, `AnalysisStore`, recording lookups); it writes its analysis through `AnalysisStore.put` after a successful call; it calls paid ports only through the wrapped ports from `build_paid_ports`; step names and `needs`/`uses` come from `JOB_PLANS` and are not redefined by steps.
- **Produces** (`nosolear.app.run_job`): `run_job(*, job_id: str, jobs: JobQueue, registry: StepRegistry) -> Job`. Behaviour: load the job; for each `StepSpec` in `JOB_PLANS[kind]` in order skip steps already DONE or SKIPPED; mark BLOCKED (`error_code="blocked"`, message "A step this one needs did not finish.") if a `needs` step is FAILED or BLOCKED; mark SKIPPED (`message="not_available"`) if no step is registered; mark SKIPPED (`"not_applicable"`) if `applies` is False; otherwise persist RUNNING, call `run`, then DONE; a `NosolearError` becomes FAILED with `error_code=e.code` and `message=e.safe_message`; any other exception becomes FAILED with `error_code="internal_error"`, message "The step failed unexpectedly." and is logged by exception type only (`logger.error("step failed: %s", type(e).__name__)`), never with the message or arguments. After every step call `jobs.update(...)` with the new `steps`, the current `step` and `progress_of(steps)`; at the end set `final_status`. Never raises for step failures.
- **Produces** (`tests/fakes.py`): `FakeStep(name, *, applies=True, raises=None, on_run=None)` recording `runs: list[StepContext]`.

- [ ] **Step 1: Write the failing tests** (`test_run_job.py`, with `FakeJobQueue`, `FakeStep`):
  - `test_runs_all_steps_in_plan_order_and_reports_progress`: five `FakeStep`s registered for ANALYZE; the job ends DONE with progress 1.0; `FakeJobQueue` recorded `update` calls show progress strictly increasing 0.2, 0.4, …, 1.0 and `step` equal to each step name in turn.
  - `test_unregistered_steps_are_skipped_not_failed`: an empty registry gives all five steps SKIPPED with message `not_available` and status DONE.
  - `test_not_applicable_step_is_skipped`: `FakeStep("probe", applies=False)` is SKIPPED with `not_applicable`, and `run` is never called.
  - `test_typed_error_becomes_failed_step_with_safe_message`: `InvalidAudio("empty")`, `CapExceeded()`, `ProviderUnavailable()`, `CapabilityMissing()` each yield FAILED with that `code` and `safe_message`.
  - `test_unexpected_exception_is_internal_error_without_text`: a step raising `RuntimeError("sk-planted-secret")` gives `error_code == "internal_error"`; the planted string appears neither in `steps`, the job, nor captured logs (`caplog`).
  - `test_failed_step_does_not_stop_independent_steps`: `score` fails: `transcribe`, `probe`, `coach` and `extract` still run; job status FAILED.
  - `test_dependent_step_is_blocked`: `transcribe` fails: `coach` is BLOCKED and never runs; `extract` still runs (it only `uses`).
  - `test_resumed_job_does_not_repeat_done_steps` (Review Focus 4): after a run where `coach` failed, `jobs.resume(id)` then `run_job` again runs only `coach` and `extract`; `score`, `transcribe`, `probe` `runs` stay at 1.
  - `test_cap_exceeded_step_fails_without_calling_provider` (the done-when cap sentence, end to end through the runner): a step calling `FakePaidPort.run` via `Meter.call` over a `FakeUsageLedger` with cap 10 and estimate 100 ends FAILED with `error_code == "cap_exceeded"` and `port.calls == 0`.
  - `test_registry_rejects_unknown_or_duplicate_step_names`.
  - `test_step_progress_within_step_is_reported`: a RESCORE `FakeStep` calling `ctx.progress(0.5)` leaves an `update` with progress 0.5 before the final 1.0.
  - `test_current_job_id_is_set_only_while_a_step_runs`: inside `run`, `current_job_id() == job.id`; before and after, `None`.
- Repository tests: `put` then `get` round-trips `raw`; a second `put` for the same `(attempt_id, kind)` returns the first row and leaves one row (`test_put_is_idempotent`); `for_attempt` lists all kinds; a `NewAnalysis` for an unknown attempt raises `IntegrityError`.

- [ ] **Step 2: Run to verify failure.** Run: `uv run pytest tests/app/test_run_job.py tests/persistence/test_repositories.py -q`. Expected: FAIL (modules missing).

- [ ] **Step 3: Implement the domain types, ports, `AnalysisRepository`, fakes, `StepRegistry` and `run_job`.**

- [ ] **Step 4: Run to verify pass.** Run: `uv run pytest tests/app tests/persistence -q`. Expected: PASS.

- [ ] **Step 5: Finish the task.** Commit message: "Add step registry and run_job use case".

---

### Task 8: Thread-pool runner, jobs API, startup recovery

**Branch:** `p0c/08-job-runner-api`

**Files:**
- Create: `apps/api/src/nosolear/adapters/thread_pool_runner.py`, `apps/api/src/nosolear/api/job_routes.py`, `apps/api/src/nosolear/api/errors.py`
- Modify: `apps/api/src/nosolear/api/deps.py` (add `Services`, `build_ledger`, `build_services`, `read_usage`, getters), `apps/api/src/nosolear/api/app.py` (lifespan, routers, `create_app` parameters), `apps/api/src/nosolear/api/schemas.py` (add `StepOut`, `JobOut`, `ErrorOut`), `apps/api/src/nosolear/app/check_readiness.py` and `cli.py` (usage figures), `tests/api/test_guards.py` (`READ_ONLY_GET_ROUTES`), regenerated `apps/web/src/shared/api/openapi.json` and `schema.d.ts`
- Test: `apps/api/tests/adapters/test_thread_pool_runner.py`, `apps/api/tests/api/test_job_api.py`, `apps/api/tests/api/test_restart.py`

**Interfaces:**
- **Consumes:** Tasks 3 to 7; 0b's `Settings` (`cap_azure_audio_hours`, `cap_azure_tts_chars`, `cap_claude_tokens`, `job_workers`), `check_readiness`, `UsageSnapshot`, `get_readiness_report`; the existing `create_app`, `_lifespan`.
- **Produces** (`nosolear.adapters.thread_pool_runner`):
  ```python
  class ThreadPoolJobRunner:
      def __init__(self, jobs: JobQueue, run: Callable[[str], object], *, workers: int, poll_seconds: float = 0.5) -> None
      def start(self) -> None
      def wake(self) -> None                       # tell idle workers to look for work now
      def run_pending(self) -> int                 # the synchronous test hook: claims and runs queued jobs in the calling
                                                   # thread until none is queued; returns how many ran (used with start_runner=False)
      def wait_idle(self, timeout: float = 10.0) -> bool   # True once no job is queued or running (threaded tests)
      def stop(self, timeout: float = 5.0) -> None
  ```
  Workers loop: `jobs.claim_next()`; if a job, `run(job.id)` (exceptions are logged by type and swallowed so a worker never dies); otherwise wait on an event for `poll_seconds`. `workers` comes from `settings.job_workers` (default 1: Azure F0 allows one concurrent request).
- **Produces** (`api/deps.py`):
  ```python
  @dataclass(frozen=True, slots=True)
  class Services:
      audio_store: AudioStore; jobs: JobQueue; ledger: UsageLedger; analyses: AnalysisStore
      registry: StepRegistry; runner: ThreadPoolJobRunner; paid_ports: dict[str, object]; clock: Clock
      # Task 9 adds: recordings: RecordingStore; attempts: AttemptReader. 0d replaces paid_ports with providers: Providers.

  def build_ledger(settings: Settings, engine: Engine, *, clock: Clock | None = None) -> UsageLedger   # SqliteUsageLedger with caps from settings
  def build_services(settings: Settings, engine: Engine, *, registry: StepRegistry | None = None, clock: Clock | None = None,
                     ledger: UsageLedger | None = None) -> Services
  def get_services(request: Request) -> Services
  def get_job_queue(request: Request) -> JobQueue
  def get_clock(request: Request) -> Clock       # every later use case reads time through this, so tests can move it
  def read_usage(settings: Settings) -> UsageSnapshot | None   # None when the database file or the usage_ledger table doesn't exist;
                                                               # never creates or migrates the database (doctor stays offline)
  ```
  `build_services` builds `build_ledger(...)` unless a ledger is passed (0e's live first run passes the user's real ledger), `SqliteJobQueue`, `FilesystemAudioStore(settings.data_dir)`, `AnalysisRepository`, `build_paid_ports`, an empty `StepRegistry` unless one is passed, and `ThreadPoolJobRunner(..., workers=settings.job_workers)`.
- **Produces** (`create_app`): `create_app(settings: Settings | None = None, *, step_registry: StepRegistry | None = None, start_runner: bool = True, ledger: UsageLedger | None = None, clock: Clock | None = None) -> FastAPI` (`clock` defaults to `SystemClock()`). Lifespan on startup: `upgrade_to_head`, `ledger.settle_open_reservations()`, `jobs.requeue_running()`, then `runner.start()` and `runner.wake()` only when `start_runner`; on shutdown: `runner.stop()`, `engine.dispose()`. `app.state.services` holds the `Services`. Tests that need determinism pass `start_runner=False` and call `app.state.services.runner.run_pending()`.
- **Produces** (readiness usage, the 0b row's real figures): `check_readiness(settings, env, *, usage: UsageSnapshot | None = None)`; `get_readiness_report` and `nosolear doctor` pass `read_usage(settings)`.
- **Produces** (HTTP):
  - `GET /api/jobs/{job_id}` → `JobOut` (`operationId getJob`); 404 `ErrorOut` for an unknown id. Side-effect free.
  - `POST /api/jobs/{job_id}/resume` → `JobOut` (`operationId resumeJob`); 404 unknown, 409 if not FAILED; wakes the runner.
  - `JobOut{id: str, kind: "analyze"|"rescore", attempt_id: str|None, status: "queued"|"running"|"done"|"failed", step: str|None, progress: float, tries: int, steps: list[StepOut]}`; `StepOut{name: str, state: "pending"|"running"|"done"|"skipped"|"failed"|"blocked", error_code: str|None, message: str|None}`; `ErrorOut{code: str, message: str}`.
  - `api/errors.py`: an exception handler mapping `NosolearError` to `ErrorOut` with status: `InvalidAudio` 400 (`too_large` 413, `bad_content_type` 415), `CapExceeded` 429, `ProviderUnavailable` 502, `CapabilityMissing` 409.

- [ ] **Step 1: Write the failing runner tests** (`test_thread_pool_runner.py`, `FakeJobQueue`):
  - `test_runs_queued_jobs_to_completion`: enqueue 3 jobs, `start()`, `wake()`, `wait_idle()` is True, and `run` was called once per job.
  - `test_worker_survives_a_raising_run`: the first job's `run` raises, the second still runs.
  - `test_stop_joins_workers`: after `stop()` no runner thread is alive.
  - `test_jobs_enqueued_after_start_are_picked_up_within_poll_interval` (with `poll_seconds=0.05`).
  - `test_run_pending_runs_every_queued_job_in_the_calling_thread`: without `start()`, three queued jobs run in the test's thread and the call returns 3; a second call returns 0.
  - `test_workers_come_from_settings`: `build_services(make_settings(data_dir=tmp_path, job_workers=2), ...)` starts two worker threads; the default starts one.
  - In `tests/test_cli.py` and `tests/app/test_check_readiness.py`: with a ledger row recorded, the usage row shows the used figures; `doctor` on a data dir without a database still prints the caps-only row and creates no file.

- [ ] **Step 2: Write the failing API tests.** `test_job_api.py` uses `loopback_client(create_app(make_settings(data_dir=tmp_path), step_registry=registry, start_runner=False))` with `FakeStep`s registered for all five analyze steps:
  - `test_get_job_shows_progress_and_steps`: enqueue through `app.state.services.jobs`, `runner.run_pending()`, `GET /api/jobs/{id}` returns `status == "done"`, `progress == 1.0`, five steps all `done`.
  - `test_get_unknown_job_is_404_with_error_body`.
  - `test_failed_job_shows_only_safe_messages`: a step raising `ProviderUnavailable` shows `error_code == "provider_unavailable"` and the fixed message; a step raising `RuntimeError("sk-planted-secret")` shows `internal_error` and the planted text appears nowhere in the response body or in the OpenAPI JSON.
  - `test_resume_endpoint`: a failed job returns to `done` after the step is fixed and `POST .../resume`; resuming a done job is 409.
  - `test_get_job_is_side_effect_free`: the jobs table is unchanged by repeated GETs.
  `test_restart.py`:
  - `test_restart_finishes_interrupted_job` (Review Focus 4, done-when): create the app once with a `FakeStep` that blocks on an event (the job is `running` with step `transcribe` running), tear the app down without letting it finish (simulating a crash: set the event only after reading the row, and mark the job rows as left over by directly leaving `status='running'`); create a second app on the same `tmp_path` with working steps; without any request the job reaches `done` and each earlier step's `runs` count is 1 across the two lifetimes for steps recorded DONE before the interruption.
  - `test_restart_settles_orphaned_reservations`: before the second start, insert a `reserved` ledger row; after startup it is `recorded` at its estimate.

- [ ] **Step 3: Run to verify failure.** Run: `uv run pytest tests/adapters/test_thread_pool_runner.py tests/api/test_job_api.py tests/api/test_restart.py -q`. Expected: FAIL.

- [ ] **Step 4: Implement the runner, schemas, errors handler, routes, `build_ledger`, `build_services`, `read_usage`, lifespan changes.** Merge with Phase 0b's changes to `create_app` (guards, middleware order) rather than overwriting them. Add `/api/jobs/{job_id}` to `READ_ONLY_GET_ROUTES`. Run `make gen-api` from the repo root and commit the regenerated web files.

- [ ] **Step 5: Run to verify pass.** Run: `uv run pytest -q` from `apps/api`, then `make gen-api` and `git diff --stat apps/web` shows only `openapi.json` and `schema.d.ts`. Expected: PASS.

- [ ] **Step 6: Finish the task.** Commit message: "Run queued jobs in a thread pool and expose job status".

---

### Task 9: Recording upload endpoint

**Branch:** `p0c/09-upload`

**Files:**
- Create: `apps/api/src/nosolear/app/upload_recording.py`, `apps/api/src/nosolear/api/recording_routes.py`
- Modify: `apps/api/src/nosolear/persistence/repositories.py` (add `RecordingRepository`, `AttemptRepository`), `apps/api/src/nosolear/ports/audio.py` (add `RecordingStore`, `AttemptReader`, `NewRecording`), `apps/api/src/nosolear/api/deps.py` (add `recordings`, `attempts` to `Services`), `apps/api/src/nosolear/api/schemas.py` (add `UploadAcceptedOut`), `apps/api/src/nosolear/api/app.py` (include router), regenerated web types
- Test: `apps/api/tests/app/test_upload_recording.py`, `apps/api/tests/api/test_recording_api.py`

**Interfaces:**
- **Consumes:** Tasks 1, 2, 6, 8 (`AudioStore`, `PendingUpload`, `JobQueue`, `Services`, `FakeAudioStore`, `FakeJobQueue`, error handler).
- **Produces** (`nosolear.ports.audio` additions):
  ```python
  @dataclass(frozen=True, slots=True)
  class NewRecording: attempt_id: str; stored: StoredRecording

  @dataclass(frozen=True, slots=True)
  class AttemptInfo: id: str; session_id: str; step: str; reference_text: str | None; scripted: bool

  class AttemptReader(Protocol):
      def exists(self, attempt_id: str) -> bool
      def get(self, attempt_id: str) -> AttemptInfo | None   # 0d's analysis steps read step, reference_text and scripted

  class RecordingStore(Protocol):
      def add_and_enqueue(self, new: NewRecording) -> tuple[Recording, Job]   # recordings row + queued ANALYZE job in ONE transaction; raises RecordingExists if the attempt already has one
      def for_attempt(self, attempt_id: str) -> Recording | None
  ```
  `class RecordingExists(ValueError)` (HTTP 409) and `class UnknownAttempt(ValueError)` (HTTP 404) in `ports/audio.py`. `RecordingRepository(engine, clock)` implements `RecordingStore`; `AttemptRepository(engine)` implements `AttemptReader` and also `create_attempt(*, session_kind: str, step: str, reference_text: str | None, scripted: bool, now: datetime) -> str` (inserts a session and an attempt, returns the attempt id; used by the CLI's `--new-attempt` in Task 10).
- **Produces** (`nosolear.app.upload_recording`): `upload_recording(*, attempt_id: str, upload: PendingUpload, attempts: AttemptReader, recordings: RecordingStore, audio: AudioStore) -> UploadResult` with `UploadResult(recording_id: str, job_id: str, duration_ms: int)`. It raises `UnknownAttempt` before committing, calls `upload.commit()`, adds the row and job, and on `RecordingExists` or any database error deletes the stored file (`audio.delete(stored.path)`) before re-raising. The caller aborts `upload` on any earlier failure.
- **Produces** (HTTP): `POST /api/attempts/{attempt_id}/recording` (`operationId uploadRecording`), request body `audio/wav` (declared with `openapi_extra` as `application/octet-stream`-free binary body `audio/wav`), 202 `UploadAcceptedOut{recording_id: str, job_id: str, duration_ms: int}`; errors `ErrorOut`: 404 unknown attempt, 409 already has a recording, 413 `too_large`, 415 wrong content type, 400 other `InvalidAudio` reasons. The route: reject unless the content type (parameters stripped, case-insensitive) is `audio/wav`; look the attempt up first; `check_declared_length(request.headers.get("content-length"))`; `upload = audio_store.begin_upload()`; `async for chunk in request.stream(): upload.write(chunk)`; `await run_in_threadpool(use_case)`; on any exception `upload.abort()`; after success `runner.wake()`.

- [ ] **Step 1: Write the failing use-case tests** (`test_upload_recording.py`, with `FakeAudioStore`, `FakeJobQueue` and an in-memory `RecordingStore` fake added to `tests/fakes.py`):
  - `test_upload_stores_recording_and_queues_analyze_job`: valid 1 s WAV in chunks gives a recording at 16 kHz, a QUEUED ANALYZE job for the attempt, `duration_ms == 1000`.
  - `test_unknown_attempt_raises_before_storing`: nothing in `FakeAudioStore.files`.
  - `test_second_upload_for_attempt_is_rejected_and_first_file_survives`: `RecordingExists`; the new file is deleted; the first remains.
  - `test_database_failure_deletes_stored_file`: a `RecordingStore` raising `OperationalError` leaves `FakeAudioStore.files` empty.

- [ ] **Step 2: Write the failing API tests** (`test_recording_api.py`, real `FilesystemAudioStore` via `loopback_client(create_app(make_settings(data_dir=tmp_path), step_registry=fake_registry, start_runner=False))`; the attempt comes from `AttemptRepository.create_attempt`):
  - `test_upload_happy_path_end_to_end`: `POST` a 48 kHz WAV with `Content-Type: audio/wav` returns 202; the file exists at `tmp_path/<path>` with a generated name and is 16 kHz; after `runner.run_pending()` the response `job_id` reads `done` through `GET /api/jobs/{id}` with the fake steps (this is the Phase 0c done-when through the API).
  - `test_attempt_reader_get_returns_step_and_reference`: `AttemptRepository.get` returns the `AttemptInfo` of a created attempt, `None` for an unknown id.
  - `test_rejects_non_wav_content_types`: `multipart/form-data`, `application/octet-stream` and a missing header give 415 and write nothing.
  - `test_unknown_attempt_is_404_and_body_is_not_read`.
  - `test_oversize_content_length_is_413_up_front`: a header of 10 MB + 1 with a tiny body gives 413 and no file in `recordings/.incoming`.
  - `test_lying_content_length_is_capped_while_streaming` (Review Focus 3): header `Content-Length: 100` with an 11 MB body streamed in chunks gives 413; a chunked request with no length gives 413; `"abc"` as the length gives 400; in every case `recordings/` holds no `.wav` and `.incoming/` is empty.
  - `test_rate_zero_header_is_400_not_500` (Review Focus 2): rate 0, 8000 and 96000 give 400 with body `{"code": "invalid_audio", ...}`.
  - `test_malformed_wavs_are_400`: stereo, 8-bit, float, two `data` chunks, truncated header, zero frames, 121 s.
  - `test_truncated_body_with_big_declared_length_uses_received_frames` (Review Focus 1): header declares 100 s of data but the body is 2 s: 202 and `duration_ms == 2000`.
  - `test_client_filename_and_query_are_ignored`: `?path=../../x&filename=../../x` and a `Content-Disposition` header never influence where the file lands.
  - `test_second_upload_is_409`.
  - `test_upload_error_bodies_contain_no_internals`: error JSON contains only `code` and `message`, no file path, no data dir.
  - `test_openapi_describes_audio_wav_body`.

- [ ] **Step 3: Run to verify failure.** Run: `uv run pytest tests/app/test_upload_recording.py tests/api/test_recording_api.py -q`. Expected: FAIL.

- [ ] **Step 4: Implement the repositories, use case, route and schemas.** `RecordingRepository.add_and_enqueue` inserts the `recordings` row and the `jobs` row in one transaction, using `initial_steps(JobKind.ANALYZE)` from the domain, and maps the unique-constraint violation on `attempt_id` to `RecordingExists`. Run `make gen-api` and commit the regenerated types.

- [ ] **Step 5: Run to verify pass.** Run: `uv run pytest -q`; `make gen-api` leaves only the expected web diff. Expected: PASS.

- [ ] **Step 6: Finish the task.** Commit message: "Add the recording upload endpoint".

---

### Task 10: CLI `upload` and `job` commands

**Branch:** `p0c/10-cli-upload`

**Files:**
- Modify: `apps/api/pyproject.toml` (move `httpx==0.28.1` from the dev group to `[project].dependencies`; `uv lock`), `apps/api/src/nosolear/cli.py`
- Create: `apps/api/src/nosolear/cli_client.py` (HTTP helpers, no argparse)
- Test: `apps/api/tests/test_cli_upload.py`

**Interfaces:**
- **Consumes:** Task 8 and 9 endpoints; 0b's `Settings.host`/`Settings.port`; `AttemptRepository.create_attempt` (Task 9); the existing `main(argv) -> int`.
- **Produces** (`nosolear.cli_client`, the one HTTP client every later CLI command uses):
  ```python
  class CliError(Exception)          # message comes from an ErrorOut body only, or a generic sentence; never response text
  class CliTimeout(CliError)

  class ApiClient:
      def __init__(self, http: httpx.Client) -> None     # tests pass loopback_client(app), which is an httpx.Client
      def get_json(self, path: str) -> Any               # non-2xx -> CliError
      def post_json(self, path: str, body: Mapping[str, object] | None = None) -> Any
      def upload_wav(self, attempt_id: str, path: Path) -> str     # POST audio/wav, streaming the file; returns the job id
      def get_job(self, job_id: str) -> dict[str, Any]
      def resume_job(self, job_id: str) -> dict[str, Any]
      def follow_job(self, job_id: str, *, out: TextIO | None = None, sleep: Callable[[float], None] = time.sleep,
                     timeout_s: float = 600.0, interval_s: float = 0.5) -> dict[str, Any]
          # blocks until done or failed and returns the final JobOut body; prints one line per change to `out` when given;
          # raises CliTimeout
  ```
  `cli.main(argv: Sequence[str] | None = None, *, client: ApiClient | None = None) -> int`: commands that talk to the API use `client`, or build `ApiClient(httpx.Client(base_url=...))` when it is `None`. 0e and Phase 1 add their commands through the same hook.
- **Produces** (CLI): `nosolear upload FILE (--attempt-id ID | --new-attempt) [--no-follow] [--base-url URL]` and `nosolear job JOB_ID [--resume] [--follow]`. Default base URL `http://{settings.host}:{settings.port}`. `--new-attempt` creates a session and attempt directly in the database and, like `dev-seed`, refuses the real `data/` directory (exit 2) so ad-hoc attempts never reach a real profile. Exit codes: 0 job done, 1 job failed, 2 usage or upload error, 3 timeout. Output lines look like `score        running  20%` and a final `job <id> done` or `job <id> failed: coach: provider_unavailable (The provider is unavailable.)`. Only job-status fields and `ErrorOut` messages are printed; the CLI sends no `Origin` header.

- [ ] **Step 1: Write the failing tests** (`test_cli_upload.py`; the client is `ApiClient(httpx.Client(transport=httpx.MockTransport(...)))` for unit tests, and the end-to-end test passes `ApiClient(loopback_client(app))` to `main`):
  - `test_upload_wav_posts_audio_wav_body`: MockTransport asserts method, path `/api/attempts/<id>/recording`, `Content-Type: audio/wav`, and that the body equals the file bytes; the return value is the job id.
  - `test_upload_error_surfaces_error_body_only`: a 413 `{"code":"invalid_audio","message":"..."}` becomes `CliError` with that message; a 500 with arbitrary text becomes a generic message without the response text.
  - `test_follow_job_prints_progress_and_returns_the_final_body`: scripted responses queued, running 20%, running 60%, done; output has one line per distinct change, no duplicates; the returned body has `status == "done"`.
  - `test_main_exit_codes`: `main(["job", ID, "--follow"], client=...)` exits 0 for done, 1 for failed (printing the safe step errors), 3 on `CliTimeout` (fake `sleep` advancing a fake clock).
  - `test_main_upload_refuses_new_attempt_on_real_data_dir` (exit 2, message on stderr), and `test_main_upload_missing_file_exits_2`.
  - `test_cli_upload_end_to_end_with_fake_steps`: build `create_app(make_settings(data_dir=tmp_path), step_registry=fakes)` (runner started), and `main(["upload", str(wav), "--attempt-id", id], client=ApiClient(loopback_client(app)))` with a synthesized WAV in `tmp_path` prints a final `done` line and exits 0 (Phase 0c done-when through the CLI).
  - `test_job_command_resume_posts_resume`.

- [ ] **Step 2: Run to verify failure.** Run: `uv run pytest tests/test_cli_upload.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement `cli_client.py`, the `client` hook on `main` and the two subcommands.** Stream the file with `httpx.Client.post(url, content=<file iterator>, headers={"Content-Type": "audio/wav"})` so a 10 MB file is not copied twice; set `Content-Length` from `Path.stat().st_size`.

- [ ] **Step 4: Run to verify pass.** Run: `uv run pytest -q`. Expected: PASS, and `uv lock --check` is clean.

- [ ] **Step 5: Finish the task.** Commit message: "Add CLI commands to upload a recording and follow its job".

---

### Task 11: Phase verification

**Branch:** `p0c/11-verification`

**Files:**
- Modify: `docs/superpowers/HANDOFF.md`; any fix the checks below demand.

**Interfaces:**
- **Consumes:** everything above.

- [ ] **Step 1: Run the whole suite.** From the repo root: `make test`, `make lint`, `make gen-api` (no diff afterwards), then `HYPOTHESIS_PROFILE=heavy uv run pytest tests/domain tests/persistence -q` from `apps/api`. Expected: all green. List the live tests: Phase 0c has none and builds no live adapter; do not run `make test-live`.

- [ ] **Step 2: Run the done-when scenario by hand** with a throwaway data dir: `export NOSOLEAR_DATA_DIR=data/dev0c`, `nosolear db upgrade`, `nosolear serve` in one terminal, then in another `nosolear upload /path/to/synthetic.wav --new-attempt` where the WAV was generated by a one-off script (never committed). Expected: the file appears under `data/dev0c/recordings/<uuid>.wav` at 16 kHz with mode 600, and the job ends `done` with every step `skipped (not_available)` because no real steps are registered yet. Kill the server mid-job with a slow fake registered, restart it, and confirm the job finishes. `git status` shows no files under `data/`.

- [ ] **Step 3: Cap check.** With `NOSOLEAR_CAP_CLAUDE_TOKENS=10` set, run the Task 7 cap test scenario through the `Meter` against the real ledger in a REPL script (not committed) and confirm `CapExceeded` with no call made. (The automated equivalent is `test_cap_exceeded_step_fails_without_calling_provider`.)

- [ ] **Step 4: Security review.** Run `/security-review` over the phase diff. Pay particular attention to: the upload path (cap, streaming, temp file location, traversal, symlinks), job status contents (`steps_json`, error messages), logs on step failure, and that no route changes state on GET. Fix findings in this branch.

- [ ] **Step 5: Update `docs/superpowers/HANDOFF.md`:** mark Phase 0c done; "Next" points at Phase 0d; copy the two sections `Produces for later phases` and `Cross-phase assumptions` from this plan as reminders; adapters unverified against the live service: unchanged (none exist). Commit, push, PR, merge per the protocol.

---

## Self-review notes

- **Spec coverage:** §13 Phase 0c items map to Tasks 1 to 2 (AudioStore, upload checks), 3 and 6 to 8 (jobs, progress, restart, `GET /api/jobs/{id}`), 4 to 5 (ledger, caps, metered decorator, composition order), 9 (endpoint), 10 (CLI). §8.1 resume semantics are in Tasks 6 and 7; §11 ledger rules in Task 4; §15 upload and traversal rows in Tasks 1, 2 and 9. §7 tables `recordings`, `jobs`, `usage_ledger`, `analyses` are Task 3. The `provider_capabilities`, `tts_cache` tables are 0d; `scoring_configs` and calibration tables 0e.
- **Decisions the spec left open, made here:** ledger quantities are integers (audio seconds rounded up) so cap arithmetic is exact; the worker count is `NOSOLEAR_JOB_WORKERS` (default 1, owner decision; F0 allows one concurrent request); step dependencies (`needs`, `uses`) and the per-kind plans live in `domain/jobs.py`; unregistered steps are SKIPPED `not_available` so the pipeline runs end to end before 0d; `--new-attempt` is a development convenience restricted to non-default data dirs; `create_app(start_runner=False)` plus `run_pending()` is the synchronous test hook every later phase uses.

## Produces for later phases

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

## Cross-phase assumptions

None open: 0b's settings tree (including `job_workers`), `make_settings`, `loopback_client`, readiness and `make test-live` are named as 0b produces them.
