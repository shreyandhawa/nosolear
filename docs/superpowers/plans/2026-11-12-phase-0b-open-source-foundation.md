# Phase 0b: Open-Source Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Nosolear safe and clear to clone and run locally: licence and community files, a validated settings tree with secret scrubbing, a readiness report (`nosolear doctor`, `GET /api/readiness`), loopback-only network guards behind `nosolear serve`, language packs wired into the profile, and CI with a dependency audit, a macOS runner and a `live` test marker.

**Architecture:** Pure domain functions decide everything new (pack validation, readiness, network policy, secret scrubbing); thin adapters read files, the environment and the filesystem; `api/deps.py` stays the composition root. Settings are the only source of configuration and keys. The profile gains a `pack_id`, and the Phase 0a `hypothesis` flag on taxonomy keys moves into the `nepali` pack's data file.

**Tech Stack:** Python 3.14, FastAPI 0.162.4, pydantic-settings 2.16.2, uvicorn 0.54.0, SQLAlchemy 2.1.8, Alembic 1.20.1, stdlib `tomllib` for pack files, pytest 9.2.0, Hypothesis 6.170.15, GitHub Actions. No new runtime dependency is expected; if one is needed, pin it with `==` and update `uv.lock`.

**Spec:** [docs/ARCHITECTURE.md](../../ARCHITECTURE.md): §13 (Phase 0b scope, authoritative), §1, §2, §3, §6.9, §10, §12, §14, §15, §16, §17. Style reference: the finished [Phase 0a plan](2026-11-11-phase-0a-foundation-and-profile-core.md).

## Global Constraints

- **Python:** 3.14, uv with `uv.lock`. New dependencies get exact pins (`==`) and an updated lockfile. Heavy local-model dependencies live only in the optional extras `local` and `apple` (§3), and adapters import them lazily. Phase 0b adds neither.
- **Commands** (from `apps/api`): `uv run pytest -q`, `uv run ruff check`, `uv run ruff format --check`, `uv run pyright` (strict for `src`). From the repo root: `make test`, `make lint`, `make gen-api`.
- **TDD for every change:** failing test first, run it, minimal code, run it, commit.
- **Layering:** the domain package has no I/O. Adapters are chosen only in `apps/api/src/nosolear/api/deps.py` (and `cli.py` through it). Every port has a fake in tests, in the style of `tests/factories.py`.
- **Hypothesis** property tests for domain logic (profiles `default` 100 examples, `heavy` 1000 via `HYPOTHESIS_PROFILE`).
- **Live tests** are marked `@pytest.mark.live`, excluded by default, run via `make test-live` (introduced here). CI never has keys.
- **Never commit audio or anything under `data/`.** Fixtures are synthetic and never hold a real voice. `scripts/check-no-personal-data.sh` runs in CI and pre-commit.
- **`apps/web`:** the only permitted change is regenerating API types with `make gen-api` (commit the regenerated files) whenever the OpenAPI schema changes, so CI's `contract` check stays green.
- **Security (owner's rules, verbatim):** Keys come only from env or .env. They never appear in logs, API responses, error messages, OpenAPI examples or fixtures. Bind to 127.0.0.1 by default, restrict CORS to the app's origin, and never expose the API unauthenticated. Uploads: cap size and duration, validate the WAV format, generate filenames server-side, write only under the data directory. Treat transcripts and coach output as untrusted. Use structured outputs with the taxonomy enum, and never let model output reach a file path, shell command or SQL string. Check the usage ledger before every paid or quota-limited call, so a bug can't burn a user's quota. Pin and lock dependencies, pin model downloads to a revision, and add a dependency audit to CI. No telemetry. Document exactly what is sent to which provider.
- **Fixed values from the spec:** default host `127.0.0.1`, port `8000`; default origins `http://localhost:5173` and `http://127.0.0.1:5173`; region pattern `^[a-z0-9]+$`; pack id pattern `^[a-z0-9_]+$`; data dir mode `0700`; MIT licence, holder "Shreyan Dhawa", year 2026; default pack `neutral` (prior `a0 = 1, b0 = 9` for every key); hypothesis prior `a0 = 1, b0 = 3`.
- **Git:** one branch and one PR per task, named `p0b/NN-<slug>`, branched from up-to-date `origin/main`. Commit and push as you go. Commit messages: an imperative sentence, **no `Co-Authored-By` trailer, no "Generated with Claude Code" footer**. Never push to `main`. Squash-merge only when CI is green, with `gh pr merge --squash` and **without** `--delete-branch` (the owner approves branch deletions).
- **Every task's PR also updates `docs/superpowers/HANDOFF.md`** (done / in progress / next; the list of adapters still unverified against a live service is "none" for this whole phase).

### Task close-out (every task ends with this step)

1. From `apps/api`: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run pyright`, all clean. From the repo root, if the task changed the OpenAPI schema: `make gen-api` and commit the regenerated files.
2. Update `docs/superpowers/HANDOFF.md`.
3. `git push -u origin <branch>`, `gh pr create --fill`, `gh pr checks --watch`.
4. When CI is green: `gh pr merge --squash` (no `--delete-branch`).

## Review Focus

Inputs most likely to bite that the spec implies but the obvious tests skip. Each has a test pinned in the task named.

1. **A key shows up somewhere a log filter doesn't look.** In a validator error (a key pasted into the region field), a chained traceback, a URL-encoded form, a message argument, or a logger configured after startup. Expect the value never to reach a terminal or log. Task 3 (`test_validation_error_hides_input`) and Task 4 (`test_scrubs_chained_traceback`, `test_scrubs_encoded_forms`, `test_scrubs_loggers_created_after_install`).
2. **Host and Origin tricks.** `Host: 127.0.0.1.evil.com`, `localhost:8000@evil.com`, a missing Host, upper-case `LOCALHOST:8000`, `Origin: null`, an origin that merely starts with an allowed one. Expect refusal for each and acceptance of `[::1]:8000`. Task 8.
3. **Peer address forms.** IPv4-mapped IPv6 (`::ffff:127.0.0.1` allowed, `::ffff:192.168.1.5` refused), no client at all, a hostname instead of an IP. Task 8.
4. **A data dir that already exists with loose permissions** (Phase 0a created `data/` as 0755 with a 0644 SQLite file), a data dir owned by someone else, and `doctor` on a fresh clone (no `.env`, no data dir) which must not create anything. Task 4 and Task 7.
5. **Bad pack input.** Pack ids such as `../x`, `NEPALI`, `a/b` or empty; malformed TOML; a missing pack directory; a pack whose `id` differs from its directory. Expect one clear error, never a stack trace, and `doctor` still printing the rest of its report. Task 5 and Task 7.

## Not in This Plan

- **Phase 0d:** `doctor --probe` behaviour (this phase registers the flag and refuses with a clear message), capability findings, transcriber speed checks, and the `local_models` marker.
- **Phase 0c:** the usage ledger. Readiness shows configured caps now and gets real usage figures when the ledger exists.
- **Phase 6:** token mode. The origin validator rejects non-loopback origins unconditionally until then.
- A scheduled (cron) audit run. The audit runs on every PR and push to `main`.

## File Map

```
LICENSE, THIRD_PARTY_NOTICES, CONTRIBUTING.md, SECURITY.md, PRIVACY.md, README.md (rewritten)
.env.example                                 every setting, commented, no values
Makefile                                     api / api-dev -> `nosolear serve`; test-live
.github/workflows/ci.yml                     api matrix + `api` gate job, audit job
scripts/third_party_licences.py              regenerates the dependency tables in THIRD_PARTY_NOTICES
content/packs/neutral/pack.toml              default pack
content/packs/nepali/pack.toml               today's hypotheses + calibration emphasis
content/calibration/items.toml               the salvaged spike items, as data
apps/api/src/nosolear/
  settings.py                                full tree (§14), validators, secret_values()
  logging_setup.py                           install_secret_scrubbing (log record factory)
  startup.py                                 prepare_process: scrubbing, HF telemetry off, private data dir
  domain/redaction.py                        scrub(text, secrets)
  domain/packs.py                            LanguagePack, parse_pack, validate_pack
  domain/calibration_items.py                CalibrationSpec, CalibrationItem, build_calibration_items
  domain/readiness.py                        ReadinessInputs -> ReadinessReport, format_readiness
  domain/network_policy.py                   peer / Host / Origin / Sec-Fetch-Site decisions
  ports/environment.py                       EnvironmentProbe protocol
  ports/stores.py                            + ProfilePackReader
  adapters/private_fs.py                     ensure_private_dir, tighten_tree, make_private_file
  adapters/content_files.py                  load_pack, load_calibration_specs (TOML)
  adapters/environment.py                    SystemEnvironment (find_spec, which, stat)
  app/ensure_profile_pack.py                 rebuild when the active pack changed
  app/check_readiness.py                     settings + environment -> ReadinessReport
  api/guards.py                              ASGI middleware over network_policy
  api/readiness_routes.py                    GET /api/readiness
  persistence/migrations/versions/0003_pack_id.py
apps/api/tests/ docs/, content/, security/, live/ plus mirrors of the above
```

---

### Task 1: Licence and community files

**Branch:** `p0b/01-community-files`

**Files:**
- Create: `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `PRIVACY.md`
- Test: `apps/api/tests/docs/test_open_source_files.py`

**Interfaces:**
- Produces: `PRIVACY.md` is the plain-words copy of §16; later phases that add a destination or change what is sent must edit it (the test pins the destinations).

- [ ] **Step 1: Write the failing tests** in `test_open_source_files.py` (read files relative to `REPO_ROOT` from `nosolear.settings`):

```python
def test_licence_is_mit_for_shreyan_dhawa_2026():
    text = read("LICENSE")
    assert text.startswith("MIT License")
    assert "Copyright (c) 2026 Shreyan Dhawa" in text
    assert "Permission is hereby granted, free of charge" in text

def test_privacy_names_every_destination_and_no_telemetry():
    text = read("PRIVACY.md")
    for needle in ("Azure Speech", "Anthropic", "Hugging Face", "never audio", "no telemetry"):
        assert needle.lower() in text.lower()

def test_security_states_single_user_machine_and_private_reporting():
    text = read("SECURITY.md").lower()
    assert "single-user machine" in text and "privately" in text
    assert "https://github.com/shreyandhawa/nosolear/security/advisories/new" in text

def test_contributing_covers_the_house_rules():
    text = read("CONTRIBUTING.md").lower()
    for needle in ("test first", "p<phase>/", "squash", "no real voices", "language pack", ".env.example"):
        assert needle in text
```

- [ ] **Step 2: Run** `uv run pytest tests/docs/test_open_source_files.py -v`. Expected: FAIL (files missing).
- [ ] **Step 3: Write the files.**
  - `LICENSE`: the standard MIT text with the fixed holder and year.
  - `PRIVACY.md`: §16's table in plain words (Azure Speech, Anthropic, Hugging Face rows exactly as the spec gives them), then "Nothing else leaves the machine", "no telemetry, analytics, crash reporting or update check", where data lives (the data dir; deleting it deletes everything), links to Microsoft's and Anthropic's data-handling terms (fetch the current URLs from the providers' official pages; do not guess), and a note that recordings are stored unencrypted (recommend FileVault or LUKS).
  - `SECURITY.md`: scope; the threat model in short (§15: loopback only, guards, secrets, uploads, supply chain); the **single-user-machine warning** (until token mode in Phase 6 any local user can call the API and spend the owner's quota); how to report privately via the GitHub advisory URL above; what not to put in a public issue (keys, recordings).
  - `CONTRIBUTING.md`: setup (`make setup`), test-first rule, the `p<phase>/NN-slug` branch and one-PR-per-task flow, squash merge when CI is green, commit style (imperative, no trailers), no real voices or keys in fixtures (including example keys; `.env.example` lists names only), the checks to run (`make test`, `make lint`), and how to add a language pack (a directory under `content/packs/<id>/` with `pack.toml`; `uv run pytest tests/content` validates it; data-only PR).
- [ ] **Step 4: Run** the test file. Expected: PASS.
- [ ] **Step 5 (owner action, document in the PR body, do not run it yourself):** enable private vulnerability reporting: `gh api -X PUT repos/shreyandhawa/nosolear/private-vulnerability-reporting`.
- [ ] **Step 6: Close out** (see Task close-out).

---

### Task 2: THIRD_PARTY_NOTICES

**Branch:** `p0b/02-third-party-notices`

**Files:**
- Create: `THIRD_PARTY_NOTICES`, `scripts/third_party_licences.py`
- Test: `apps/api/tests/docs/test_notices.py`

**Interfaces:**
- Produces: `scripts/third_party_licences.py` with `--check` (exit 1 if the generated tables differ from the file) and no flag (rewrite the tables between the markers `<!-- python-dependencies:start/end -->` and `<!-- web-dependencies:start/end -->`). Run it from the repo root with `uv run --project apps/api python scripts/third_party_licences.py`. Any later task that adds a dependency reruns it.

- [ ] **Step 1: Write the failing tests** in `test_notices.py`:

```python
def test_every_locked_python_package_is_listed():
    locked = {normalize(p["name"]) for p in tomllib.loads(read("apps/api/uv.lock"))["package"]} - {"nosolear"}
    assert locked <= listed_python_names(read("THIRD_PARTY_NOTICES"))

def test_every_direct_web_dependency_is_listed():
    pkg = json.loads(read("apps/web/package.json"))
    names = set(pkg.get("dependencies", {})) | set(pkg.get("devDependencies", {}))
    assert names <= listed_web_names(read("THIRD_PARTY_NOTICES"))

@pytest.mark.parametrize("component", ["CrisperWhisper", "espeak-ng", "wav2vec2-lv-60-espeak-cv-ft", "Whisper"])
def test_component_section_has_source_and_verification_date(component):
    section = section_for(read("THIRD_PARTY_NOTICES"), component)
    assert re.search(r"Source: https://", section) and re.search(r"Verified: 20\d\d-\d\d-\d\d", section)

def test_crisperwhisper_is_flagged_non_commercial_and_opt_in():
    s = section_for(read("THIRD_PARTY_NOTICES"), "CrisperWhisper").lower()
    assert "non-commercial" in s and "opt-in" in s and "mit licence does not cover" in s

def test_espeak_is_gpl_separate_executable():
    s = section_for(read("THIRD_PARTY_NOTICES"), "espeak-ng")
    assert "GPL-3.0" in s and "separate executable" in s and "phonemizer" in s
```

(`normalize` = PEP 503 name normalisation; the three helpers parse the markdown tables / `## <component>` sections.)

- [ ] **Step 2: Run** `uv run pytest tests/docs/test_notices.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement `scripts/third_party_licences.py`.** Python rows come from `importlib.metadata` of the project environment (`License-Expression`, else the `License` field, else `License ::` classifiers; "UNKNOWN: check upstream" when none). Web rows come from `pnpm licenses list --json` run in `apps/web`. Output a table of name, version, licence per ecosystem. The script reads no network.
- [ ] **Step 4: Write `THIRD_PARTY_NOTICES`.** Intro (the repo ships no weights, binaries or audio; the MIT licence covers only this project's own code), a hand-written `## <component>` section for each row of §17's table (CrisperWhisper, espeak-ng, wav2vec2-lv-60-espeak-cv-ft weights, Whisper weights for mlx-whisper and faster-whisper), then the two generated tables. **For each component, verify the licence from the upstream source at implementation time** (the project's repository licence file and, for weights, the Hugging Face model card; use the Fetch tools) and record `Source: <url>` and `Verified: <today>` lines. State the licence you actually found. If it differs from the spec's expectation (CrisperWhisper non-commercial; espeak-ng GPL-3.0; the others "confirm"), keep the verified text, and record the discrepancy in `HANDOFF.md` and in the PR body so ARCHITECTURE.md §17/§18 gets corrected. If a source cannot be reached, do not guess a date or licence: stop and report instead.
- [ ] **Step 5: Run** the script, then the tests. Expected: PASS; `--check` exits 0.
- [ ] **Step 6: Close out.**

---

### Task 3: Settings tree and `.env.example`

**Branch:** `p0b/03-settings-tree`

**Files:**
- Modify: `apps/api/src/nosolear/settings.py`, `apps/api/src/nosolear/cli.py` (catch `ValidationError` in `main`), `apps/api/tests/conftest.py` (autouse env cleaner), `apps/api/tests/factories.py` (`make_settings`), `.env.example`
- Test: `apps/api/tests/test_settings.py` (extend), `apps/api/tests/test_cli.py` (extend), `apps/api/tests/docs/test_env_example.py`

**Interfaces:**
- Consumes: the existing `Settings.data_dir` and `database_url`.
- Produces (all in `nosolear/settings.py`):

```python
LOOPBACK_NAMES: frozenset[str]            # {"localhost", "127.0.0.1", "::1"}
TRANSCRIBERS = ("auto", "mlx_whisper", "faster_whisper", "azure_stt", "crisper_whisper")

class Settings(BaseSettings):
    data_dir: Path
    host: str                              # default "127.0.0.1"; loopback only
    port: int                              # default 8000; 1..65535
    app_origins: tuple[str, ...]           # comma-separated in env; loopback hosts only
    azure_speech_key: SecretStr | None
    azure_speech_region: str | None        # ^[a-z0-9]+$
    azure_locale: str                      # default "en-US"; ^[a-z]{2,3}-[A-Z]{2}$
    tts_voice: str                         # default "en-US-JennyNeural"; ^[A-Za-z0-9-]+$
    anthropic_api_key: SecretStr | None
    coach_model: str                       # default "claude-opus-5-5"; ^[A-Za-z0-9._-]+$
    transcriber: Literal["auto", "mlx_whisper", "faster_whisper", "azure_stt", "crisper_whisper"]
    pack: str                              # default "neutral"; ^[a-z0-9_]+$
    cap_azure_audio_hours: float           # default 4.5, > 0
    cap_azure_tts_chars: int               # default 450000, > 0
    cap_claude_tokens: int                 # default 100000, > 0
    def secret_values(self) -> tuple[str, ...]      # non-empty configured secrets, in field order
    @property
    def packs_dir(self) -> Path                     # REPO_ROOT / "content" / "packs"

def settings_error_summary(exc: ValidationError) -> str
    # one line per error: "NOSOLEAR_<FIELD>: <message>"; never the input value
```
`model_config` adds `hide_input_in_errors=True`.

- [ ] **Step 1: Write the failing tests** (use `make_settings(**kw)` = `Settings(_env_file=None, **kw)` so the developer's real `.env` never leaks in; the autouse fixture deletes every `NOSOLEAR_*` variable):

```python
def test_defaults(): ...  # host "127.0.0.1", port 8000, origins == ("http://localhost:5173","http://127.0.0.1:5173"), pack "neutral", transcriber "auto", caps 4.5 / 450000 / 100000, coach_model "claude-opus-5-5"
@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.5", "example.com", "::", ""]) 
def test_non_loopback_host_rejected(host): ...
@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost", "127.0.0.2"]) 
def test_loopback_host_accepted(host): ...
@pytest.mark.parametrize("origin", ["https://example.com", "http://192.168.1.5:5173", "http://100.64.0.1:5173",
    "http://localhost:5173/path", "ftp://localhost", "http://user@localhost", "null", "*"])
def test_non_loopback_or_malformed_origin_rejected(origin): ...
def test_origins_parse_comma_list_and_normalise(monkeypatch):
    monkeypatch.setenv("NOSOLEAR_APP_ORIGINS", "http://localhost:3000/, http://[::1]:3000,http://localhost:3000")
    assert make_settings().app_origins == ("http://localhost:3000", "http://[::1]:3000")
@pytest.mark.parametrize("region", ["westus2", "eastus"])  # accepted
@pytest.mark.parametrize("region", ["West US", "west-us", "a.b", "x/../y", "evil.com#", "WESTUS"])  # rejected
@pytest.mark.parametrize("pack", ["../x", "NEPALI", "a/b", "a b", "x.y"])  # rejected
def test_voice_model_locale_patterns(): ...
def test_secret_fields_mask_in_repr_and_dump():
    s = make_settings(azure_speech_key="k" * 32, anthropic_api_key="a" * 40)
    assert "k" * 32 not in repr(s) and "k" * 32 not in str(s.model_dump()) and "a" * 40 not in s.model_dump_json()
def test_secret_values_lists_only_configured_keys(): ...
def test_validation_error_hides_input():
    secret = "SECRET_pasted_into_the_wrong_field_123"
    with pytest.raises(ValidationError) as e:
        make_settings(azure_speech_region=secret)
    assert secret not in str(e.value) and secret not in settings_error_summary(e.value)
    assert "NOSOLEAR_AZURE_SPEECH_REGION" in settings_error_summary(e.value)
def test_cli_reports_bad_settings_without_input(monkeypatch, capsys):
    monkeypatch.setenv("NOSOLEAR_HOST", "0.0.0.0")
    assert main(["rebuild-profile"]) == 2
    err = capsys.readouterr().err
    assert "NOSOLEAR_HOST" in err and "0.0.0.0" not in err
```

`test_env_example.py`: every `Settings` field appears in `.env.example` as a commented or uncommented `NOSOLEAR_<FIELD>=` line; no line assigns a value to a key-like setting (`*_KEY`, `*_API_KEY`); no line matches a long token pattern (`[A-Za-z0-9_-]{24,}`) after `=`.

- [ ] **Step 2: Run** `uv run pytest tests/test_settings.py tests/test_cli.py tests/docs/test_env_example.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the fields above. Notes that fix choices: use `Annotated[tuple[str, ...], NoDecode]` plus a `mode="before"` validator that splits a comma-separated string; the origin validator parses with `urllib.parse.urlsplit`, requires scheme `http`/`https`, no userinfo/path/query/fragment, `hostname in LOOPBACK_NAMES`, rebuilds the canonical `scheme://host[:port]` (brackets for IPv6), de-duplicates in order. The error messages must not contain the offending value and must say "token mode is not available until Phase 6" for the origin case. The host validator uses `ipaddress.ip_address(...).is_loopback` or the literal `localhost`. `cli.main` constructs `Settings()` inside `try/except ValidationError` and prints `settings_error_summary` to stderr, returning 2.
- [ ] **Step 4: Rewrite `.env.example`** to list every setting with a one-line comment and its default, key lines empty (`# NOSOLEAR_AZURE_SPEECH_KEY=`), keeping the existing `NOSOLEAR_DATA_DIR` text.
- [ ] **Step 5: Run** the full suite. Expected: PASS (existing `Settings(data_dir=tmp_path)` callers unchanged).
- [ ] **Step 6: Close out.**

---

### Task 4: Secret scrubbing and private data dir

**Branch:** `p0b/04-scrubbing-and-private-data-dir`

**Files:**
- Create: `apps/api/src/nosolear/domain/redaction.py`, `apps/api/src/nosolear/logging_setup.py`, `apps/api/src/nosolear/adapters/private_fs.py`, `apps/api/src/nosolear/startup.py`
- Modify: `apps/api/src/nosolear/cli.py`, `apps/api/src/nosolear/api/app.py` (lifespan calls `prepare_process`)
- Test: `apps/api/tests/domain/test_redaction.py`, `apps/api/tests/test_logging_setup.py`, `apps/api/tests/adapters/test_private_fs.py`, `apps/api/tests/test_startup.py`

**Interfaces:**
- Consumes: `Settings.secret_values()`, `Settings.data_dir` (Task 3).
- Produces:

```python
# domain/redaction.py
MIN_SECRET_LENGTH = 8     # shorter values are not scrubbed: they would shred ordinary text
REDACTED = "[redacted]"
def scrub(text: str, secrets: Iterable[str]) -> str
    # also scrubs URL-quoted, quote_plus, JSON-escaped and repr-escaped forms; longest secret first

# logging_setup.py
def install_secret_scrubbing(secrets: Iterable[str]) -> None   # idempotent; replaces earlier secrets
def uninstall_secret_scrubbing() -> None                       # restores the original factory (tests)

# adapters/private_fs.py
class DataDirError(RuntimeError)
def ensure_private_dir(path: Path) -> None     # mkdir -p, mode 0700; raises DataDirError if not owned by us
def tighten_tree(path: Path) -> None           # dirs under path 0700, files 0600; symlinks are skipped
def make_private_file(path: Path) -> None      # chmod 0600; used by AudioStore (0c) and the TTS cache (0d)

# startup.py
def prepare_process(settings: Settings, *, create_data_dir: bool) -> None
    # install_secret_scrubbing(settings.secret_values()); os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1");
    # if create_data_dir: ensure_private_dir(data_dir) then tighten_tree(data_dir)
```

- [ ] **Step 1: Write the failing tests.**
  - `test_redaction.py`: `scrub("key=SECRETSECRET1", ["SECRETSECRET1"]) == "key=[redacted]"`; a secret of 7 chars is left alone; URL-quoted, `quote_plus`, JSON-escaped (`"a\"b..."`) and `repr`-escaped forms of a secret containing `"`/space/`/` are scrubbed; two secrets where one contains the other are both removed; `scrub(text, [])` returns `text`. Hypothesis property: for any `prefix`, `suffix` text and a secret of length >= 8, `secret not in scrub(prefix + secret + suffix, [secret])`.
  - `test_logging_setup.py` (fixture calls `uninstall_secret_scrubbing()` afterwards; capture with a handler on the logger, formatted through `logging.Formatter`):
    `test_scrubs_message_and_args` (`log.info("key %s", key)` and an f-string message), `test_scrubs_traceback` (`raise ValueError(f"bad {key}")` logged with `log.exception`), `test_scrubs_chained_traceback` (`raise RuntimeError("outer") from ValueError(key)`), `test_scrubs_encoded_forms` (key in a logged URL, percent-encoded), `test_scrubs_loggers_created_after_install` (a new `logging.getLogger("late")` with its own new handler), `test_second_install_replaces_secrets`, `test_mismatched_format_args_do_not_crash` (`log.info("%s %s", key)` still logs, scrubbed, no exception).
  - `test_private_fs.py`: a 0755 dir containing a 0644 file and a nested 0755 dir becomes 0700/0600/0700 via `tighten_tree`; `ensure_private_dir` on a new nested path creates 0700; on an existing 0755 dir tightens to 0700; a dir owned by another uid (monkeypatch `os.stat` result uid) raises `DataDirError`; a symlink inside the tree is not followed and not chmod-ed (target keeps its mode); `make_private_file` gives 0600.
  - `test_startup.py`: `prepare_process(settings, create_data_dir=False)` does not create a missing data dir; with `True` the Phase 0a layout (a pre-existing dir with `nosolear.sqlite`, `-wal`, `-shm` at 0644) ends 0700/0600; `HF_HUB_DISABLE_TELEMETRY` is `"1"` afterwards and a pre-set value is kept; after `prepare_process` with a planted key, logging a message containing it is scrubbed. In `test_cli.py`: `main(["db", "upgrade"])` on a loose-permission data dir leaves it 0700.
- [ ] **Step 2: Run** the four test files. Expected: FAIL (modules missing).
- [ ] **Step 3: Implement `scrub`** (pure; build the variant set per secret, sort by length descending, replace). 
- [ ] **Step 4: Implement `install_secret_scrubbing`** by wrapping `logging.getLogRecordFactory()` once. The wrapper calls the original factory, then sets `record.msg = scrub(record.getMessage(), secrets)` and `record.args = None` (fall back to `scrub(f"{msg} {args}")` if `getMessage` raises); if `record.exc_info` holds an exception, sets `record.exc_text = scrub("".join(traceback.format_exception(*record.exc_info)).rstrip("\n"), secrets)` (the stdlib `Formatter` reuses a non-empty `exc_text`, and `format_exception` follows `__cause__`/`__context__` chains); scrubs `stack_info` the same way. A record factory is used instead of handler filters so handlers and loggers created later (uvicorn's) are covered.
- [ ] **Step 5: Implement `private_fs` and `startup.prepare_process`** as specified; `tighten_tree` uses `os.walk(followlinks=False)` and `os.chmod` only on non-symlink entries. Wire `prepare_process(settings, create_data_dir=True)` into `cli.main` (all commands except the `doctor` command added in Task 7, which passes `False`) before the engine is created, and into `api/app.py`'s lifespan before the engine is created.
- [ ] **Step 6: Run** the full suite. Expected: PASS.
- [ ] **Step 7: Close out.**

---

### Task 5: Language packs

**Branch:** `p0b/05-language-packs`

**Files:**
- Create: `apps/api/src/nosolear/domain/packs.py`, `apps/api/src/nosolear/domain/calibration_items.py`, `apps/api/src/nosolear/adapters/content_files.py`, `content/packs/neutral/pack.toml`, `content/packs/nepali/pack.toml`, `content/calibration/items.toml`
- Test: `apps/api/tests/domain/test_packs.py`, `apps/api/tests/domain/test_calibration_items.py`, `apps/api/tests/adapters/test_content_files.py`, `apps/api/tests/content/test_shipped_content.py`

**Interfaces:**
- Consumes: `Taxonomy`/`DEFAULT_TAXONOMY` (`__contains__` accepts listed and well-formed dynamic keys), `Prior`, `HYPOTHESIS_PRIOR`, `DEFAULT_PRIOR` from `domain/estimates.py`, `Settings.packs_dir`.
- Produces:

```python
# domain/packs.py
PACK_ID_PATTERN = r"^[a-z0-9_]+$"
MAX_PRIOR_MASS = 20.0                     # a0 + b0 above this is "out of range": one baseline must outweigh any prior
class PackError(ValueError)               # malformed structure or failed validation; message lists every problem

@dataclass(frozen=True, slots=True)
class PackHypothesis:
    key: str
    reason: str
    prior: Prior

@dataclass(frozen=True, slots=True)
class CalibrationExtra:
    key: str
    word: str
    respelling: str | None

@dataclass(frozen=True, slots=True)
class LanguagePack:
    id: str
    name: str
    description: str
    default_prior: Prior
    hypotheses: tuple[PackHypothesis, ...]
    calibration_emphasis: tuple[str, ...]
    calibration_extras: tuple[CalibrationExtra, ...]
    def prior_for(self, key: str) -> Prior          # hypothesis prior if listed, else default_prior

def parse_pack(raw: Mapping[str, object]) -> LanguagePack     # structure/type errors -> PackError
def validate_pack(pack: LanguagePack, taxonomy: Taxonomy) -> tuple[str, ...]   # () when valid

# domain/calibration_items.py
@dataclass(frozen=True, slots=True)
class CalibrationSpec:
    error_key: str
    description: str
    words: tuple[tuple[str, str], ...]        # (word, respelling)
@dataclass(frozen=True, slots=True)
class CalibrationItem:
    id: str
    word: str
    error_key: str
    deliberate: bool
    instruction: str
def parse_calibration_specs(raw: Mapping[str, object]) -> tuple[CalibrationSpec, ...]
def validate_calibration_specs(specs: Sequence[CalibrationSpec], taxonomy: Taxonomy) -> tuple[str, ...]
def build_calibration_items(specs: Sequence[CalibrationSpec]) -> tuple[CalibrationItem, ...]

# adapters/content_files.py
def load_pack(packs_dir: Path, pack_id: str) -> LanguagePack      # PackError for any failure
def list_pack_ids(packs_dir: Path) -> tuple[str, ...]
def load_calibration_specs(path: Path) -> tuple[CalibrationSpec, ...]
```

**Pack file schema (`pack.toml`):**

```toml
id = "nepali"                # must equal the directory name
name = "Nepali"
description = "..."
[default_prior]              # optional; default a0 = 1, b0 = 9
a0 = 1
b0 = 9
[[hypotheses]]               # zero or more; prior optional, default a0 = 1, b0 = 3
key = "sound.sub.v.w"
reason = "one line"
[calibration]
emphasis = ["sound.sub.v.w"] # keys to calibrate first; may be empty
[[calibration.extras]]       # optional extra items for those keys
key = "sound.sub.v.w"
word = "vine"
respelling = "wine"          # optional
```

**Calibration file schema (`content/calibration/items.toml`):** `[[specs]]` with `error_key`, `description`, and `words = [["vest", "west"], ...]`.

- [ ] **Step 1: Write the failing domain tests.**

```python
def test_prior_for_uses_hypothesis_then_default():
    pack = parse_pack({... one hypothesis "sound.sub.v.w" ...})
    assert pack.prior_for("sound.sub.v.w") == Prior(1, 3)
    assert pack.prior_for("sound.sub.f.p") == Prior(1, 9)

@pytest.mark.parametrize("bad", [...])   # each: missing id; id "NEPALI"/"a/b"/""; empty name; empty reason;
def test_parse_or_validate_reports(bad): ...  # unknown key "grammar.artcle"; key "sound.sub.v"; duplicate hypothesis key;
                                              # a0 = 0, b0 = -1, a0 = nan, a0 + b0 = 21; emphasis key unknown; duplicate emphasis key;
                                              # extra with whitespace-only word; word longer than 40 chars; wrong types (a0 = "1")
def test_validate_returns_every_problem_not_just_the_first(): ...
def test_valid_pack_has_no_problems(): ...
```

  Add a Hypothesis property: for any finite `a0, b0 > 0` with `a0 + b0 <= MAX_PRIOR_MASS`, a pack with that default prior validates; for any `a0 + b0 > MAX_PRIOR_MASS` it does not.
  `test_calibration_items.py`: with the shipped specs, `len(build_calibration_items(specs)) == 78`; ids unique; for `("vest", "west")` the ids are `vest__correct`, `vest__err1`, `vest__err2`, with `deliberate` False/True/True and instructions exactly `Say "vest" as correctly as possible, in General American.` and `Say "vest" with W instead of V: sounds like "west" (take 1 of 2)`; for the epenthesis key the deliberate text is `Say "school" with a vowel before it: "ischool" (take 1 of 2)`; every spec key is in `DEFAULT_TAXONOMY`; an unknown key yields a problem string.
  `test_content_files.py` (tmp dirs): loads a valid pack; ids `../x`, `NEPALI`, `a/b`, `""` raise `PackError` before any file access (assert with a directory that would otherwise exist); malformed TOML, missing directory, `id` differing from the directory, a `pack.toml` over 64 KiB, and a symlinked pack directory that resolves outside `packs_dir` each raise `PackError` with a one-line message; `list_pack_ids` returns sorted directory names that match the pattern.
  `test_shipped_content.py`: for every id in `list_pack_ids(Settings.packs_dir)`, `load_pack(...)` succeeds (this is the gate a contributed pack runs through); `neutral` has no hypotheses and `default_prior == Prior(1, 9)`; `nepali.calibration_emphasis` is the ten spike keys in spike order (`sound.sub.v.w`, `sound.sub.w.v`, `sound.sub.f.p`, `sound.sub.θ.t`, `sound.sub.ð.d`, `sound.sub.ʃ.s`, `sound.sub.s.ʃ`, `sound.sub.z.dʒ`, `sound.sub.z.s`, `sound.ins.epenthesis_sC`) and each has at least one spec in `items.toml`; **the characterisation test of today's priors:**

```python
PHASE_0A_HYPOTHESIS_KEYS = {  # keys whose taxonomy flag `hypothesis` was True in Phase 0a
    "sound.sub.v.w", "sound.sub.w.v", "sound.sub.f.p", "sound.sub.ʃ.s", "sound.sub.s.ʃ",
    "sound.sub.θ.t", "sound.sub.z.dʒ", "sound.sub.z.s", "sound.sub.ð.d", "sound.sub.ʒ.dʒ",
    "sound.sub.i.ɪ", "sound.sub.ɪ.i", "sound.sub.æ.ɛ", "sound.sub.ʌ.ɑ",
    "sound.low.t", "sound.low.d", "sound.low.ɹ", "sound.low.ɝ", "sound.low.θ", "sound.low.ð",
    "sound.ins.epenthesis_sC", "prosody.word_stress", "prosody.unexpected_break", "prosody.monotone",
    "grammar.article", "grammar.preposition",
}
def test_nepali_hypotheses_are_exactly_the_phase_0a_flags():
    pack = load_pack(packs_dir, "nepali")
    assert {h.key for h in pack.hypotheses} == PHASE_0A_HYPOTHESIS_KEYS
    assert all(h.prior == Prior(1, 3) and h.reason for h in pack.hypotheses)
```

- [ ] **Step 2: Run** the four test files. Expected: FAIL.
- [ ] **Step 3: Implement `domain/packs.py`.** `parse_pack` checks only structure and types (collecting all problems into one `PackError`); `validate_pack` checks the id pattern, non-empty text, finite priors with `a0 > 0`, `b0 > 0`, `a0 + b0 <= MAX_PRIOR_MASS`, keys in the taxonomy, no duplicate hypothesis or emphasis keys, extras (key in taxonomy; word 1 to 40 characters, no control characters). `PackError` messages never include more than the offending field name and a short reason.
- [ ] **Step 4: Implement `adapters/content_files.py`.** `load_pack` rejects an id that fails `PACK_ID_PATTERN` before touching the filesystem, resolves `packs_dir / id / "pack.toml"` and refuses a path whose resolved parent is not inside `packs_dir.resolve()`, refuses files over 64 KiB, parses with `tomllib` (turn `TOMLDecodeError` and `OSError` into `PackError`), requires `pack.id == pack_id`, runs `validate_pack(pack, DEFAULT_TAXONOMY)` and raises `PackError("; ".join(problems))`.
- [ ] **Step 5: Port the spike items.** `git show p0b/spikes:spikes/items.py` is the source. The `_SPEC` mapping becomes `content/calibration/items.toml` (10 specs, 26 words, same descriptions and respellings, same order). `_build` becomes `build_calibration_items` (same ids, same three items per word, the instruction formats pinned in Step 1; the em dash in the spike strings becomes a colon). The spike's `READ_ALOUD`, `FREE_TALK_PROMPT` and `record.py` are **not** ported: baseline content is written for the project in Phase 0e. Phase 0e extends the set to the 5-error-token minimum per key (the salvaged set has two to four words per key).
- [ ] **Step 6: Write the pack files.** `neutral`: id, name "Neutral", description "No first-language assumptions. Every key starts at the same weak prior.", no hypotheses, empty emphasis. `nepali`: description drawn from §6.9's sound-system summary; one `[[hypotheses]]` entry for each of the 26 keys above with a one-line `reason` taken from §6.9's list (consonant substitutions, inserted vowel before s-clusters, retroflex-sounding t/d seen as low accuracy, vowel contrasts, rhotic r and r-colored vowel, flapped t and weak forms, stress and rhythm, articles and prepositions); `emphasis` = the ten spike keys in order; no extras.
- [ ] **Step 7: Run** the full suite. Expected: PASS.
- [ ] **Step 8: Close out.**

---

### Task 6: Wire the active pack into the profile

**Branch:** `p0b/06-pack-in-profile`

**Files:**
- Modify: `domain/taxonomy.py` (remove `hypothesis` from `KeyDefinition` and its builders), `domain/profile.py`, `app/rebuild_profile.py`, `ports/stores.py`, `persistence/models.py`, `persistence/repositories.py`, `api/deps.py`, `api/app.py`, `cli.py`, `dev/seed.py` (only if it references the flag), existing tests listed below
- Create: `persistence/migrations/versions/0003_pack_id.py`, `app/ensure_profile_pack.py`
- Test: `tests/domain/test_profile.py`, `tests/domain/test_taxonomy.py`, `tests/domain/test_profile_properties.py`, `tests/persistence/test_repositories.py`, `tests/persistence/test_schema.py`, `tests/app/test_rebuild_profile.py`, `tests/app/test_ensure_profile_pack.py`, `tests/test_cli.py`, `tests/api/test_profile_api.py`, `tests/factories.py`

**Interfaces:**
- Consumes: `LanguagePack`, `load_pack`, `PackError` (Task 5); `Settings.pack`, `Settings.packs_dir`.
- Produces:

```python
# domain/profile.py
def build_profile(observations, *, as_of, taxonomy, pack: LanguagePack, config=DEFAULT_CONFIG) -> Profile
@dataclass(frozen=True, slots=True)
class Profile:  # gains
    pack_id: str
# domain/taxonomy.py: KeyDefinition loses `hypothesis`; `prior_for` in profile.py is removed.

# ports/stores.py
class ProfilePackReader(Protocol):
    def latest_pack_id(self) -> str | None: ...

# app/rebuild_profile.py
def rebuild_profile(*, observations, profiles, taxonomy, pack: LanguagePack, clock, config=DEFAULT_CONFIG) -> Profile
# app/ensure_profile_pack.py
def ensure_profile_pack(*, observations, profiles: ProfileWriter & ProfilePackReader, taxonomy, pack, clock) -> bool
    # rebuilds (reason "rebuild") and returns True iff a profile exists and its pack_id != pack.id

# api/deps.py
def load_active_pack(settings: Settings) -> LanguagePack     # PackError propagates
# persistence: profile_entries.pack_id and profile_snapshots.pack_id, TEXT NOT NULL
```
Test helpers in `tests/factories.py`: `NEPALI`, `NEUTRAL` (loaded with `load_pack(REPO_ROOT / "content" / "packs", ...)`) and `PACK = NEPALI`.

- [ ] **Step 1: Write the failing tests.** Update every existing `build_profile(..., taxonomy=TAX)` call to pass `pack=PACK` (`NEPALI` keeps the Phase 0a numbers: for example `(a, b) == (11, 33)` for `sound.sub.v.w`). Then add:
  - `test_neutral_pack_uses_default_prior_for_every_key`: one v/w miss gives `(a, b) == (2, 9)` under `NEUTRAL` and `(2, 3)` under `NEPALI`.
  - `test_profile_records_pack_id`: `build_profile(..., pack=NEUTRAL).pack_id == "neutral"`.
  - Properties in `test_profile_properties.py`: `test_changing_pack_changes_only_priors` (for any observation list, entries built under two packs have identical `(a - a0, b - b0)` evidence sums but possibly different `p_hat`); the existing properties keep passing with `pack=PACK`.
  - `test_taxonomy.py`: delete `test_hypothesis_keys_present` and the `.hypothesis` assertions; keep every other assertion.
  - `test_repositories.py`: `save` then `latest()` round-trips `pack_id`; `latest_pack_id()` is `None` on an empty DB and the saved id afterwards; the snapshot row stores `pack_id`.
  - `test_schema.py`: existing drift test passes with the new column; add `test_migration_0003_backfills_nepali`: upgrade to `0002`, insert a profile entry and snapshot row, upgrade to head, both rows have `pack_id == "nepali"` (Phase 0a rows were built with today's hypothesis priors).
  - `test_ensure_profile_pack.py`: no profile yet returns `False` and writes nothing; same pack returns `False` with no new snapshot; different pack returns `True`, writes one snapshot, and the new profile's `pack_id` is the new pack's.
  - `test_cli.py`: `rebuild-profile` with `NOSOLEAR_PACK=neutral` after seeding under `nepali` yields profile entries whose p_hat differs, and `latest_pack_id() == "neutral"`; `NOSOLEAR_PACK=nosuchpack` exits 2 with a message that names the pack and contains no traceback; `NOSOLEAR_PACK=../x` exits 2 (Task 3's validator).
  - `test_profile_api.py`: a TestClient app started over a DB whose stored profile used `nepali` while `NOSOLEAR_PACK=neutral` rebuilds on startup (`latest_pack_id() == "neutral"` after the lifespan runs); an invalid pack does not stop startup (the pack error is left for readiness to show).
- [ ] **Step 2: Run** `uv run pytest -q`. Expected: FAIL (signature errors, missing column).
- [ ] **Step 3: Remove the flag.** Before deleting it, confirm Task 5's list: `uv run python -c "from nosolear.domain.taxonomy import DEFAULT_TAXONOMY as T; print(sorted(d.key for d in T.defined() if d.hypothesis))"` must print exactly the 26 keys of `PHASE_0A_HYPOTHESIS_KEYS` (stop and report if it does not). Then drop the field, the `hypothesis` parameters of `_definition`, `_sub`, `_low`, and the hypothesis argument of `_dynamic`'s definitions.
- [ ] **Step 4: Implement** `build_profile(..., pack)` (priors come from `pack.prior_for(defn.key)`, `Profile.pack_id = pack.id`), the model/migration/repository changes (`0003_pack_id.py`: `op.add_column` on both tables with `server_default="nepali"`, `nullable=False`; the model columns carry no server default; downgrade drops them in a batch), `rebuild_profile(pack=...)`, and `ensure_profile_pack`.
- [ ] **Step 5: Wire it.** `deps.load_active_pack(settings)` calls `load_pack(settings.packs_dir, settings.pack)`. `api/app.py`'s lifespan, after `upgrade_to_head`, tries `ensure_profile_pack(...)` with the active pack and catches `PackError` (logged as a warning with the safe message). `cli.py`'s `rebuild-profile` and `dev-seed` use `load_active_pack`; a `PackError` prints `pack error: <message>` to stderr and returns 2.
- [ ] **Step 6: Run** the full suite. Expected: PASS. `make gen-api` should produce no diff (the profile response schema is unchanged); confirm with `git diff --stat apps/web`.
- [ ] **Step 7: Close out.**

---

### Task 7: Readiness: domain, `nosolear doctor`, `GET /api/readiness`

**Branch:** `p0b/07-readiness`

**Files:**
- Create: `domain/readiness.py`, `ports/environment.py`, `adapters/environment.py`, `app/check_readiness.py`, `api/readiness_routes.py`
- Modify: `api/schemas.py`, `api/deps.py`, `api/app.py` (include router), `cli.py`, `tests/factories.py` (`FakeEnvironment`), regenerated `apps/web/src/shared/api/*`
- Test: `tests/domain/test_readiness.py`, `tests/app/test_check_readiness.py`, `tests/adapters/test_environment.py`, `tests/api/test_readiness_api.py`, `tests/test_cli.py` (extend)

**Interfaces:**
- Consumes: `Settings` (Task 3), `prepare_process` (Task 4), `load_pack`/`validate_pack`/`PackError` (Task 5), `make_settings`.
- Produces:

```python
# domain/readiness.py
class Component(StrEnum):   # values are the wire ids
    AZURE_SPEECH = "azure_speech"; AZURE_CAPABILITIES = "azure_capabilities"; ANTHROPIC = "anthropic"
    TRANSCRIBER = "transcriber"; PHONE_PROBE = "phone_probe"; LANGUAGE_PACK = "language_pack"
    DATA_DIR = "data_dir"; USAGE = "usage"
class ReadinessStatus(StrEnum):
    READY = "ready"; MISSING = "missing"; NOT_INSTALLED = "not_installed"
    NOT_PROBED = "not_probed"; DEGRADED = "degraded"

@dataclass(frozen=True, slots=True)
class PackStatus:        pack_id: str; name: str | None; hypotheses: int; problems: tuple[str, ...]
@dataclass(frozen=True, slots=True)
class CapabilityFindings: nbest: bool; prosody: bool; probed_on: date          # produced by Phase 0d; always None in 0b
@dataclass(frozen=True, slots=True)
class UsageSnapshot:     azure_audio_hours: float; tts_chars: int; claude_tokens: int   # produced by Phase 0c; None in 0b
@dataclass(frozen=True, slots=True)
class Caps:              azure_audio_hours: float; tts_chars: int; claude_tokens: int
@dataclass(frozen=True, slots=True)
class ReadinessInputs:
    azure_key_set: bool; azure_region: str | None; azure_locale: str
    anthropic_key_set: bool; coach_model: str
    transcriber: str; modules: frozenset[str]; espeak_installed: bool; system: str; machine: str
    pack: PackStatus
    data_dir: str; data_dir_mode: int | None; env_file_mode: int | None
    caps: Caps; usage: UsageSnapshot | None; capabilities: CapabilityFindings | None
@dataclass(frozen=True, slots=True)
class ReadinessRow:      component: Component; status: ReadinessStatus; reason: str; fix: str | None
@dataclass(frozen=True, slots=True)
class ReadinessReport:
    rows: tuple[ReadinessRow, ...]          # always the eight components, in the enum order
    @property
    def ready(self) -> bool                 # no row is MISSING
def build_readiness(inputs: ReadinessInputs) -> ReadinessReport
def format_readiness(report: ReadinessReport) -> str

# ports/environment.py
class EnvironmentProbe(Protocol):
    def module_available(self, name: str) -> bool: ...
    def executable_available(self, name: str) -> bool: ...
    def path_mode(self, path: Path) -> int | None: ...      # None when the path does not exist
    def platform(self) -> tuple[str, str]: ...              # (sys.platform-style system, machine)

# app/check_readiness.py
def check_readiness(settings: Settings, env: EnvironmentProbe) -> ReadinessReport
# api/deps.py
def get_settings(request: Request) -> Settings
def get_environment() -> EnvironmentProbe       # SystemEnvironment()
# api/schemas.py
class ReadinessRowOut(BaseModel): component: Literal[...8 ids...]; label: str; status: Literal[...5...]; reason: str; fix: str | None
class ReadinessOut(BaseModel):    ready: bool; rows: list[ReadinessRowOut]
```
Route: `GET /api/readiness`, `operation_id="getReadiness"`. CLI: `nosolear doctor [--probe]`.

**Row rules** (fixed by the spec's table in §14 and the example; wording is the implementer's, the statuses and fixes are not):
- **Azure Speech:** key and region set -> READY (`key set, region <r>, locale <l>`); either missing -> MISSING with the fix naming the exact variables to set in `.env`.
- **Azure capabilities:** Azure Speech not ready -> NOT_PROBED (fix: configure Azure first); `capabilities is None` -> NOT_PROBED (fix: ``run `nosolear doctor --probe` (available from Phase 0d)``); otherwise READY (`n-best yes/no, prosody yes/no (probed <date>)`), DEGRADED if either is false.
- **Anthropic:** key set -> READY (`key set, model <id>`); else MISSING with the fix.
- **Transcriber:** explicit `azure_stt` needs Azure configured; `mlx_whisper` needs module `mlx_whisper` (fix ``uv sync --extra apple``); `faster_whisper` needs `faster_whisper`, `crisper_whisper` needs `torch` and `transformers` (fix ``uv sync --extra local``); a missing library is NOT_INSTALLED. `auto` follows §5.1's order without speed data: darwin/arm64 `mlx_whisper`, `faster_whisper`, `azure_stt`; linux `faster_whisper`, `azure_stt`; any other platform `azure_stt`; the first usable one is READY with `auto -> <name> (speed not yet checked)`; none usable -> MISSING. `crisper_whisper` explicit adds "non-commercial licence, opt-in" to the reason.
- **Phone probe:** modules `torch` and `transformers` plus the `espeak-ng` executable -> READY; otherwise NOT_INSTALLED with the fix ``run `uv sync --extra local`, then install espeak-ng`` (never MISSING: it is optional).
- **Language pack:** `problems` empty -> READY (`<id> (<name>), <n> hypotheses`); else MISSING (`pack '<id>' is invalid: <problems>`, fix: edit `content/packs/<id>/pack.toml` or set `NOSOLEAR_PACK`).
- **Data dir:** missing -> READY (`will be created on first start`); mode with any group/other bit set -> DEGRADED (fix ``chmod 700 <dir>``; `nosolear serve` tightens it on start); `.env` with any group/other bit set -> DEGRADED (fix ``chmod 600 .env``); both can be reported in one reason.
- **Usage:** always READY; reason shows the configured caps, plus used figures when `usage` is given (`Azure 0.4 of 4.5 h, TTS 12k of 450k chars, Claude 3k of 100k tokens today`); without usage it adds that usage tracking arrives with the ledger.
- **Never in any field:** a key, a fragment, its length or a hash (inputs carry only booleans), or a provider error body.

- [ ] **Step 1: Write the failing domain tests** (`test_readiness.py`, built on a `make_inputs(**overrides)` helper with sensible ready defaults): one test per row rule above asserting `status` and that `fix` names the exact variable or command (`"NOSOLEAR_ANTHROPIC_API_KEY"`, `"uv sync --extra local"`, `"chmod 700"`); `test_report_has_eight_rows_in_enum_order`; `test_ready_false_only_when_a_row_is_missing`; `test_auto_transcriber_order` parametrised over (`darwin`,`arm64`, modules) and (`linux`,`x86_64`, modules); `test_format_readiness_columns` (one line per row: label, status text, reason; fixes on an indented line); Hypothesis property `test_no_row_text_contains_a_planted_secret` building inputs from arbitrary text for region, model id, locale, pack name and asserting only that those exact fields can appear (inputs have no key field, so a planted key string put nowhere in the inputs never appears).
- [ ] **Step 2: Write the failing app, adapter, API and CLI tests.**
  - `test_check_readiness.py` with `FakeEnvironment(modules=..., executables=..., modes={path: mode}, platform=("darwin","arm64"))` and `make_settings(data_dir=tmp_path, ...)`: a fresh-clone case (no keys, no `.env`, no data dir) yields MISSING for Azure Speech and Anthropic, READY data dir, and **creates nothing on disk** (assert `tmp_path` stays empty); an invalid pack id in settings (`pack="nosuchpack"`) gives a MISSING pack row and the other seven rows still compute; planted keys never appear in `repr(report)`.
  - `test_environment.py`: `SystemEnvironment.module_available("json") is True`, `("definitely_not_a_module_xyz") is False` and importing must not happen (a module in `sys.modules` count is unchanged for a module that exists on disk but is unimported; use `importlib.util.find_spec` only); `executable_available("sh")` True; `path_mode` of a tmp file with `chmod 0o640` returns `0o640` and `None` for a missing path.
  - `test_readiness_api.py`: `GET /api/readiness` returns 200 with eight rows and the key `ready`; with planted keys configured the response text contains neither key; the OpenAPI document contains `/api/readiness` and no occurrence of the planted keys; the call writes nothing under the data dir.
  - `test_cli.py` additions: `main(["doctor"])` prints a line containing `Azure Speech` and returns 1 when keys are missing, 0 when `NOSOLEAR_AZURE_SPEECH_KEY`, `..._REGION` and `NOSOLEAR_ANTHROPIC_API_KEY` are set (use planted values; assert they are absent from stdout and stderr); `doctor` creates no data dir; `main(["doctor", "--probe"])` returns 2 and prints `probes arrive in Phase 0d`; `doctor` with `NOSOLEAR_PACK=nosuchpack` still prints all eight rows.
- [ ] **Step 3: Run** the new tests. Expected: FAIL.
- [ ] **Step 4: Implement** `domain/readiness.py` per the rules; `SystemEnvironment` (`find_spec`, `shutil.which`, `os.stat` mode `& 0o777`, `sys.platform`/`platform.machine()`); `check_readiness` (reads settings, calls the environment probe, loads the pack with `load_pack` and `validate_pack` turning `PackError` into `problems`, maps secrets to booleans, `usage=None`, `capabilities=None`, `.env` path `REPO_ROOT / ".env"`); `deps.get_settings` / `get_environment`; the route and schemas (map `ReadinessReport` to `ReadinessOut`, `label` from a fixed dict in the route module); the `doctor` subcommand (`prepare_process(settings, create_data_dir=False)`, print `format_readiness`, exit 1 when not ready; `--probe` prints the Phase 0d message to stderr and returns 2).
- [ ] **Step 5: Run** the full suite, then `make gen-api` and commit the regenerated files under `apps/web/src/shared/api/`. Expected: PASS and a diff limited to those files.
- [ ] **Step 6: Close out.**

---

### Task 8: Network guards, `nosolear serve`, Makefile

**Branch:** `p0b/08-network-guards-and-serve`

**Files:**
- Create: `domain/network_policy.py`, `api/guards.py`
- Modify: `api/app.py` (guards + CORS), `cli.py` (`serve`), `Makefile` (`api`, `api-dev`), `tests/factories.py` (`loopback_client`), `tests/api/conftest.py`, `tests/api/test_health.py`
- Test: `tests/domain/test_network_policy.py`, `tests/api/test_guards.py`, `tests/test_cli.py` (extend), `tests/test_makefile.py`

**Interfaces:**
- Consumes: `Settings.host`, `.port`, `.app_origins`, `LOOPBACK_NAMES` (Task 3); `prepare_process` (Task 4).
- Produces:

```python
# domain/network_policy.py   (pure; no I/O)
def peer_is_loopback(host: str | None) -> bool
    # accepts 127.0.0.0/8, ::1 and IPv4-mapped loopback; refuses None, hostnames, everything else
def allowed_hosts(port: int, app_origins: Sequence[str]) -> frozenset[str]
    # {"127.0.0.1:<port>", "localhost:<port>", "[::1]:<port>"} plus the netloc of each app origin, lower-case
def host_is_allowed(header: str | None, allowed: frozenset[str]) -> bool      # exact, case-insensitive membership
def origin_is_allowed(header: str | None, app_origins: Sequence[str]) -> bool
    # header None -> True; "null" -> False; otherwise exact membership
def fetch_site_is_allowed(header: str | None) -> bool                          # only "cross-site" is refused
def check_request(*, peer: str | None, host: str | None, origin: str | None, fetch_site: str | None,
                  port: int, app_origins: Sequence[str]) -> str | None
    # None when allowed, else a short fixed reason code: "peer", "host", "origin", "fetch_site" (checked in that order)

# api/guards.py
class RequestGuardMiddleware:   # pure ASGI; http and websocket scopes; lifespan passes through
    def __init__(self, app: ASGIApp, *, port: int, app_origins: Sequence[str]) -> None
# refusal: 403, JSON {"detail": "request refused"}; the reason code is logged at WARNING, never header values

# cli.py
# `nosolear serve [--reload]`: refuses non-loopback (via Settings) and runs
# uvicorn.run("nosolear.api.app:create_app", factory=True, host=settings.host, port=settings.port,
#             reload=args.reload, proxy_headers=False)
# tests/factories.py
def loopback_client(app: FastAPI) -> TestClient   # base_url http://127.0.0.1:8000, client=("127.0.0.1", 50000)
```

Middleware order in `create_app`: CORS (`allow_origins=list(settings.app_origins)`, `allow_methods=["GET","POST","PUT","DELETE"]`, `allow_headers=["content-type"]`, `allow_credentials=False`, never `*`) is added first and `RequestGuardMiddleware` last, so the guard is outermost and refuses before CORS answers anything.

- [ ] **Step 1: Write the failing tests.**
  - `test_network_policy.py`:

```python
@pytest.mark.parametrize("peer,ok", [("127.0.0.1", True), ("127.5.5.5", True), ("::1", True),
    ("::ffff:127.0.0.1", True), ("::ffff:192.168.1.5", False), ("192.168.1.5", False),
    ("10.0.0.2", False), ("localhost", False), ("testclient", False), ("", False), (None, False)])
def test_peer_is_loopback(peer, ok): assert peer_is_loopback(peer) is ok

@pytest.mark.parametrize("host,ok", [("127.0.0.1:8000", True), ("localhost:8000", True), ("LOCALHOST:8000", True),
    ("[::1]:8000", True), ("localhost:5173", True), ("127.0.0.1.evil.com:8000", False),
    ("localhost:8000@evil.com", False), ("evil.com", False), ("localhost", False), ("localhost:9999", False),
    ("", False), (None, False), ("localhost:8000, evil.com", False)])
def test_host_is_allowed(host, ok): ...   # port 8000, default origins

# origin: None -> True; "http://localhost:5173" True; "null" False; "http://localhost:5173.evil.com" False;
# "http://localhost:5173/" False (browsers never send a trailing slash); "https://localhost:5173" False; "*" False
# fetch_site: "same-origin", "same-site", "none", None -> True; "cross-site" -> False
# check_request returns "peer" before "host" before "origin" before "fetch_site" when several fail
```
    Hypothesis properties: for any `junk` of length >= 1 over printable characters, `origin_is_allowed("http://localhost:5173" + junk, DEFAULTS)` and `host_is_allowed("localhost:8000" + junk, allowed)` are False; `origin_is_allowed("null", [... even if "null" were configured ...])` is False.
  - `test_guards.py` (app built with `make_settings(data_dir=tmp_path)`):
    `test_loopback_peer_and_host_pass` (`GET /api/health` 200); `test_non_loopback_peer_refused` (`TestClient(app, client=("192.168.1.5", 4000))` -> 403 for `/api/health` and `/api/profile`, even with a valid Host); `test_foreign_host_refused` (`Host: evil.com`, and `127.0.0.1.evil.com:8000`); `test_vite_proxy_host_allowed` (`Host: localhost:5173`); `test_origin_null_refused`; `test_foreign_origin_refused_on_post_and_get`; `test_allowed_origin_passes`; `test_sec_fetch_site_cross_site_refused`; `test_refusal_body_is_fixed_and_leaks_nothing` (body equals `{"detail": "request refused"}` and does not contain the offending header value); `test_cors_preflight_for_allowed_origin_only` (OPTIONS with `Origin: http://localhost:5173` and `Access-Control-Request-Method: POST` -> 200 with `access-control-allow-origin` equal to that origin; a foreign origin -> 403 with no `access-control-allow-origin`); `test_cors_never_wildcard`; `test_no_cookies_set` (no `set-cookie` header on any response); `test_get_routes_are_declared_read_only`:

```python
READ_ONLY_GET_ROUTES = {"/api/health", "/api/profile", "/api/readiness"}   # later phases add theirs deliberately
def test_get_routes_are_declared_read_only(app):
    gets = {r.path for r in app.routes if isinstance(r, APIRoute) and "GET" in r.methods and r.path.startswith("/api")}
    assert gets == READ_ONLY_GET_ROUTES
```
  - `test_cli.py`: `NOSOLEAR_HOST=0.0.0.0 nosolear serve` returns 2, prints a message naming `NOSOLEAR_HOST`, and never calls `uvicorn.run` (monkeypatched to fail); a normal `serve` calls `uvicorn.run` with `host="127.0.0.1"`, `port=8000`, `factory=True`, `proxy_headers=False`, `reload=False`; `serve --reload` passes `reload=True`.
  - `test_makefile.py`: the `api` and `api-dev` recipes contain `nosolear serve` and not `uvicorn`; no recipe contains `0.0.0.0`.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement** `network_policy` as exact-membership checks (build the allowed set once; lower-case hosts; compare origins exactly). Implement the middleware: for `http`/`websocket` scopes read `scope["client"][0]` (None if absent), the `host`, `origin` and `sec-fetch-site` headers (first value), call `check_request`; on refusal log the reason code and send the 403 (for websockets close with code 1008); otherwise pass through.
- [ ] **Step 4: Implement `serve`** (settings already refuse a non-loopback host; `prepare_process(settings, create_data_dir=True)` runs inside the app lifespan so reload workers also run it). `proxy_headers=False` keeps `scope["client"]` the real socket peer, so a forwarded-for header cannot change it. Update `Makefile`: `api` -> `cd apps/api && uv run nosolear serve --reload`; `api-dev` -> the same with `NOSOLEAR_DATA_DIR=$(CURDIR)/data/dev`.
- [ ] **Step 5: Update existing API tests** to build clients with `loopback_client(create_app(...))` (the default `testserver` host and `testclient` peer are now refused, which is the point).
- [ ] **Step 6: Run** the full suite. Expected: PASS. Smoke check once by hand: `make api` in one terminal, `curl -s -H 'Host: evil.com' http://127.0.0.1:8000/api/health` prints the refusal body, `curl -s http://127.0.0.1:8000/api/health` prints `{"status":"ok"}`.
- [ ] **Step 7: Close out.**

---

### Task 9: CI: audit, macOS runner, `live` marker

**Branch:** `p0b/09-ci-audit-macos-live`

**Files:**
- Modify: `.github/workflows/ci.yml`, `apps/api/pyproject.toml` (pytest `markers`, `addopts`), `Makefile` (`test-live`), `apps/api/tests/conftest.py`
- Create: `apps/api/tests/live/conftest.py`, `apps/api/tests/live/test_live_environment.py`
- Test: `apps/api/tests/test_pytest_config.py`, `apps/api/tests/live/test_live_helpers.py`

**Interfaces:**
- Produces: marker `live`; `make test-live`; fixtures in `tests/live/conftest.py` that Phases 0d/0e use:

```python
@pytest.fixture
def live_settings(tmp_path) -> Settings        # real env and .env, but data_dir=tmp_path (never the real data dir)
def require_keys(settings: Settings, *providers: Literal["azure", "anthropic"]) -> None   # pytest.skip when unset
```
CI job names after this task: `hygiene`, `api` (gate), `api-matrix` (legs `api (ubuntu-latest)`, `api (macos-latest)`), `web`, `contract`, `audit`.

- [ ] **Step 1: Write the failing tests.**
  - `test_pytest_config.py`: reads `pytestconfig`: `"live" in "\n".join(pytestconfig.getini("markers"))`; `"--strict-markers" in pytestconfig.getini("addopts")` and `"not live" in " ".join(pytestconfig.getini("addopts"))`.
  - `test_live_helpers.py`: `require_keys` skips (use `pytest.raises(pytest.skip.Exception)`) when the key is unset and returns when set; `live_settings.data_dir` is under `tmp_path` and differs from `REPO_ROOT / "data"`.
  - `live/test_live_environment.py`: one `@pytest.mark.live` test, `test_live_settings_never_use_the_real_data_dir`, that needs no keys (so `make test-live` has something to run and never exits 5 on an empty selection).
- [ ] **Step 2: Run** `uv run pytest tests/test_pytest_config.py -v`. Expected: FAIL.
- [ ] **Step 3: Configure pytest.** In `pyproject.toml`: `markers = ["live: calls real Azure or Claude, or loads real local models; run with make test-live"]` and `addopts = "--strict-markers -m 'not live'"`. `Makefile`: `test-live:` runs `cd apps/api && uv run pytest -q -m live` (a later `-m` on the command line overrides the `addopts` one). Add `test-live` to `.PHONY`.
- [ ] **Step 4: Run** the suite: the live test is deselected (`1 deselected`); then `make test-live` runs exactly that one test and passes without keys.
- [ ] **Step 5: Rewrite `ci.yml`.**
  - `api-matrix`: `name: api (${{ matrix.os }})`, `strategy.fail-fast: false`, `matrix.os: [ubuntu-latest, macos-latest]`, same steps as today's `api` job.
  - `api`: the gate job, `needs: api-matrix`, `if: always()`, a step that fails unless `needs.api-matrix.result == 'success'`. It keeps the required check name `api` stable, so branch protection needs no change for the matrix.
  - `audit` (ubuntu): `astral-sh/setup-uv`, then `uv export --locked --no-emit-project --all-extras --format requirements-txt -o "$RUNNER_TEMP/requirements.txt"` in `apps/api` (works with no extras defined, covers `local` and `apple` once they exist), then `uvx --from pip-audit==<version> pip-audit -r "$RUNNER_TEMP/requirements.txt" --no-deps --disable-pip`; and in `apps/web`: pnpm setup as in the `web` job, `pnpm install --frozen-lockfile`, `pnpm audit --audit-level=high`. Look up the current `pip-audit` release at implementation time (`uv pip index versions pip-audit` or PyPI) and pin it exactly; keep the action versions the file already uses. A vulnerability with no fix may be waived only with `--ignore-vuln <ID>` plus a comment naming the advisory and the reason.
- [ ] **Step 6: Open the PR and watch CI.** Expected: `hygiene`, `api (ubuntu-latest)`, `api (macos-latest)`, `api`, `web`, `contract`, `audit` all green. If `pip-audit` or `pnpm audit` flags a real advisory, upgrade the pinned dependency (exact pin, lockfile updated) rather than waiving it, unless no fixed version exists.
- [ ] **Step 7: Close out, then update branch protection** (owner-approved step; `audit` can only be required after it has reported once, which this PR's run did). `api` is already required and now stands for both matrix legs:

```bash
gh api -X PATCH repos/shreyandhawa/nosolear/branches/main/protection/required_status_checks \
  -f 'contexts[]=hygiene' -f 'contexts[]=api' -f 'contexts[]=web' -f 'contexts[]=contract' -f 'contexts[]=audit'
gh api repos/shreyandhawa/nosolear/branches/main/protection -q '.required_status_checks.contexts'
```
  Expected output of the second command: `["hygiene","api","web","contract","audit"]`.

---

### Task 10: README setup guide

**Branch:** `p0b/10-readme-setup-guide`

**Files:**
- Modify: `README.md` (rewrite)
- Test: `apps/api/tests/docs/test_readme.py`

**Interfaces:**
- Consumes: Makefile targets (`setup`, `api`, `web`, `test`, `lint`, `test-live`, `seed`), CLI subcommands (`doctor`, `serve`, `db`, `rebuild-profile`, `dev-seed`), `.env.example`.

- [ ] **Step 1: Write the failing tests** in `test_readme.py`:

```python
def test_every_make_target_in_readme_exists():       # regex `make ([a-z-]+)` inside backticks; targets parsed from Makefile
def test_every_nosolear_subcommand_in_readme_exists():   # regex `nosolear ([a-z-]+)`; subcommands from cli._parser()
def test_every_env_var_in_readme_is_a_setting():     # `NOSOLEAR_[A-Z_]+` all map to a Settings field
def test_readme_has_required_sections():
    text = read("README.md")
    for heading in ("Platforms", "Prerequisites", "Get your keys", "Set up", "Check your setup", "Optional extras",
                    "What leaves your machine", "Costs", "Security"):
        assert f"## {heading}" in text
def test_readme_warns_about_single_user_machines_and_links_licence_files():
    text = read("README.md").lower()
    assert "single-user machine" in text and "third_party_notices" in text and "privacy.md" in text and "security.md" in text
def test_readme_no_longer_describes_a_nepali_only_app(): assert "native nepali speaker" not in text.lower()
```

- [ ] **Step 2: Run** `uv run pytest tests/docs/test_readme.py -v`. Expected: FAIL.
- [ ] **Step 3: Write the README.** Mirror §1/§2/§11/§16/§17. Content, in order: what it is (open-source, local, bring-your-own-keys English speaking coach, any first language; three skills; the ~15-minute loop); status (backend first; the web UI arrives in Phase 2; say plainly what works today: `make seed`, the profile page, `doctor`, `serve`); **Platforms** (macOS on Apple Silicon and Linux x86-64 first-class and tested in CI; Windows via WSL2); **Prerequisites** per platform (Homebrew or apt, `uv`, Node and `pnpm` versions from `.node-version`, Git; `espeak-ng` only for the later `local` extra); **Get your keys** (Azure: create a Speech resource on the F0 tier, the free account asks for a non-prepaid card and a phone number with a temporary $1 hold, set a $1 budget alert; Anthropic: create a key in the Console, ideally in a workspace with a spend limit; put them in `.env`, never in chat or issues); **Set up** (`git clone`, `make setup`, `cp .env.example .env`, edit keys, `NOSOLEAR_PACK` for a language pack); **Check your setup** (`nosolear doctor`, what each status means, that it never prints a key; ``nosolear doctor --probe`` arrives in Phase 0d); **Run** (`make api`, `make web`, the app origins); **Optional extras** (`uv sync --extra local` and `--extra apple` arrive in Phase 0d, with sizes to be added then; full-disk encryption recommended); **What leaves your machine** (the §16 table in short, link PRIVACY.md); **Costs** (the §2/§11 figures: F0 free, about $7 a month on the default Claude model, prices dated 2026-11-11 and subject to each provider's terms, caps configurable); **Security** (loopback only, **single-user machine warning** stated plainly, link SECURITY.md); **Licence** (MIT, link `LICENSE`, `THIRD_PARTY_NOTICES`, CrisperWhisper non-commercial note); **Contributing** (link). Keep the existing privacy sentence about `data/` being git-ignored.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Follow the README yourself** from a clean checkout in a temp directory (`git clone` the branch, `make setup`, `cp .env.example .env`, `uv run nosolear doctor`): every command works as written, the doctor report shows Azure Speech and Anthropic as missing, no key is printed. Fix the README where it is wrong.
- [ ] **Step 6: Close out.**

---

### Task 11: Planted-fake-key test (the harness later phases extend)

**Branch:** `p0b/11-planted-key-test`

**Files:**
- Create: `apps/api/tests/security/__init__.py`, `apps/api/tests/security/planted.py`, `apps/api/tests/security/test_no_key_leaks.py`
- Modify: `apps/api/tests/conftest.py` (none expected; the helpers live in `planted.py`)

**Interfaces:**
- Consumes: `make_settings`, `loopback_client`, `create_app`, `install_secret_scrubbing`, `main`, `Settings`.
- Produces (the contract Phases 0c, 0d and 0e extend):

```python
# tests/security/planted.py
PLANTED_AZURE_KEY: str        # 32 chars, obviously fake, e.g. "FAKEAZUREKEY" + 20 filler characters; never a real-looking key
PLANTED_ANTHROPIC_KEY: str    # 40 chars, e.g. "sk-ant-FAKEKEY" + filler
PLANTED: tuple[str, ...]
def planted_settings(data_dir: Path, **overrides) -> Settings          # both keys set, region "westus2"
def assert_no_planted_key(*surfaces: str | bytes | Mapping | Sequence, where: str) -> None
    # fails, naming `where` only (never the key), if any planted key or a quoted/URL-encoded/JSON-escaped form appears
    # in any surface, recursively through dicts and lists
LEAK_SURFACES: list[Callable[[Path], tuple[str, str]]]
    # registry of (where, text) producers; each takes a tmp data dir. Later phases append: adapter error paths with fake transports,
    # `jobs.steps_json`, the ledger tables, the coach prompt log
def leak_surface(fn): ...      # decorator that appends fn to LEAK_SURFACES
```
`test_no_key_leaks.py` parametrises over `LEAK_SURFACES`, so adding a surface adds a test case with no edit to the test.

- [ ] **Step 1: Write the failing tests / surfaces** (each surface is a `@leak_surface` function; the parametrised test calls it and runs `assert_no_planted_key`):
  - `settings_repr_str_dump_json`: `repr`, `str`, `model_dump()`, `model_dump_json()` of the planted settings.
  - `log_message_args_and_fstring` and `log_exception_with_key_in_message` and `log_chained_exception`, after `install_secret_scrubbing(settings.secret_values())`, captured through a real handler and `Formatter`.
  - `api_readiness_response`: body and headers of `GET /api/readiness`.
  - `api_health_and_profile_responses`.
  - `openapi_schema`: `json.dumps(app.openapi())`.
  - `api_unhandled_error_response_and_log`: a test-only route on the app raising `RuntimeError(f"boom {PLANTED_AZURE_KEY}")`; client built with `raise_server_exceptions=False`; the 500 body and the captured log text are clean.
  - `doctor_output`: stdout and stderr of `main(["doctor"])` with the planted keys in the environment.
  - `validation_error_text`: `str(ValidationError)` and `settings_error_summary` from settings built with a planted key in the region field.
  - `cli_bad_settings_stderr`: `main([...])` with `NOSOLEAR_AZURE_SPEECH_REGION` set to the planted key.
  - `env_example_and_repo_files`: the text of `.env.example` and `README.md` (no planted key, which also proves fixtures never need to hold one).
  - Meta-tests: `test_assert_no_planted_key_detects_plain_quoted_and_urlencoded_forms` (the helper itself fails when a key is present in each form, including inside a nested dict), and `test_registry_is_not_empty`.
- [ ] **Step 2: Run** `uv run pytest tests/security -v`. Expected: the meta-tests fail first (helper missing); once the helper exists, every surface must pass without further production-code change. Any surface that fails is a real leak: fix the production code (not the test) and note it in the PR body.
- [ ] **Step 3: Implement** `planted.py`. Keep the planted values syntactically unlike real keys of either provider and obviously fake, and make sure they contain no characters that would need escaping in a way the helper does not also check.
- [ ] **Step 4: Run** the full suite and `make lint`. Expected: PASS.
- [ ] **Step 5: Close out.** In the PR body and `HANDOFF.md`, state: "Later phases append `@leak_surface` producers for their adapter error paths, job `steps_json`, ledger rows and logs."

---

### Task 12: Phase 0b verification and security review

**Branch:** `p0b/12-phase-verification`

**Files:**
- Modify: `docs/superpowers/HANDOFF.md`, `docs/ARCHITECTURE.md` only if Task 2 found a licence discrepancy or the owner answers an open question below (a small, separate commit)

- [ ] **Step 1: Whole-phase checks** from a clean state (`git switch main && git pull`): `make setup`, `make test`, `make lint`, `make gen-api` (no diff), `HYPOTHESIS_PROFILE=heavy uv run pytest -q tests/domain` (from `apps/api`), `make test-live` (passes without keys; list that the live adapters are none yet).
- [ ] **Step 2: Walk the "done when" of §13 by hand** and note each result in the PR body: on a fresh clone (temp directory) follow the README to `nosolear doctor` and confirm it lists what is configured and missing without revealing any key (set planted keys in `.env` and `grep` the output); `NOSOLEAR_HOST=0.0.0.0 uv run nosolear serve` refuses; with `make api` running, `curl` a request with `Host: evil.com`, one with `Origin: https://evil.example`, and one with `Origin: null` — each gets 403 — and `uvicorn nosolear.api.app:create_app --factory --host 0.0.0.0` answers a request from a second machine or interface address with 403 (if no second host is available, rely on the TestClient peer test and say so); CI on the final PR is green on Ubuntu and macOS with `audit`.
- [ ] **Step 3: Run `/security-review`** on the whole phase's diff (`git diff <phase-start-sha>..main`). Fix every finding in a task-sized PR before the handoff (branch `p0b/12-security-fixes`), or record accepted risks in `HANDOFF.md` with the owner's name against each.
- [ ] **Step 4: Update `HANDOFF.md`:** mark Phase 0b done; list what Phase 0c can rely on (the section below); Next = plan and execute Phase 0c; adapters unverified against live services: none exist yet.
- [ ] **Step 5: Close out** (PR with `HANDOFF.md`, squash-merge when green).

---

## Self-Review

- **Spec coverage (§13 Phase 0b):** LICENSE, README, THIRD_PARTY_NOTICES, CONTRIBUTING, SECURITY, PRIVACY (Tasks 1, 2, 10); settings tree with SecretStr, validators, log scrubbing, data-dir tightening (3, 4); readiness, `doctor`, `GET /api/readiness` (7); guards, `serve`, Makefile (8); audit, macOS, `live` marker, `make test-live`, branch-protection command (9); packs with `neutral`, `nepali`, spike items, pack in the profile (5, 6); planted-key test (11); phase gate (12). §15 rows for 0b: network, origins, DNS rebinding, CSRF, data dir, keys in logs/API/OpenAPI/repo, supply chain audit: all have a task and a test. §14's `doctor` warning on a group-readable `.env` is in Task 7. §6.9's "changing the pack triggers a rebuild" is `ensure_profile_pack` in Task 6.
- **Deviations from the literal spec, flagged for the reviewer:** (1) `doctor --probe` and capability findings are stubbed to Phase 0d, as §13 allows. (2) The usage row shows caps only until Phase 0c has a ledger. (3) Secrets shorter than 8 characters are not scrubbed (they would corrupt ordinary log text); real provider keys are far longer. (4) `proxy_headers=False` in `serve` so forwarded-for headers cannot alter the peer address; Phase 6 revisits it for Tailscale Serve.
- **Type consistency:** `LanguagePack`/`PackError`/`load_pack` (Task 5) are the names Tasks 6 and 7 use; `Settings.secret_values`, `packs_dir` (Task 3) are used in Tasks 4, 6, 7; `make_settings`, `loopback_client` (Tasks 3, 8) are used by Tasks 7, 8, 11; `prepare_process(settings, create_data_dir=...)` (Task 4) is called by Tasks 7 and 8.
- **Proportion:** tasks carry signatures, file names, test names and the fixed values; bodies are left to the implementer except the two algorithms the signature does not fix (the log record factory and the Host/Origin exact-membership rule).

## Produces for later phases

- `Settings` tree and `LOOPBACK_NAMES`; `Settings.secret_values()`; `Settings.packs_dir`; `settings_error_summary(exc)`.
- `domain/redaction.scrub`, `logging_setup.install_secret_scrubbing`, `startup.prepare_process(settings, *, create_data_dir)`.
- `adapters/private_fs.py`: `ensure_private_dir`, `tighten_tree`, `make_private_file(path)` (0c's `AudioStore` and 0d's TTS cache call `make_private_file` on every file they write).
- `LanguagePack`, `PackHypothesis`, `CalibrationExtra`, `parse_pack`, `validate_pack`, `load_pack`, `list_pack_ids`; `CalibrationSpec`, `CalibrationItem`, `build_calibration_items`, `load_calibration_specs` (0e's calibration reads `LanguagePack.calibration_emphasis` and `calibration_extras`, and extends `content/calibration/items.toml`).
- `build_profile(..., pack)`, `rebuild_profile(..., pack)`, `Profile.pack_id`, `ProfilePackReader`, `deps.load_active_pack(settings)`; tables `profile_entries.pack_id` and `profile_snapshots.pack_id` (migration `0003`).
- Readiness: `ReadinessInputs` (with `capabilities: CapabilityFindings | None` and `usage: UsageSnapshot | None` for 0d and 0c to fill), `build_readiness`, `check_readiness(settings, env)`, `EnvironmentProbe`, `GET /api/readiness` (`getReadiness`), `nosolear doctor` (`--probe` currently refuses with exit 2).
- Network: `domain/network_policy.check_request`, `RequestGuardMiddleware`, `nosolear serve [--reload]`; every new `GET /api/...` route must be added to `READ_ONLY_GET_ROUTES` in `tests/api/test_guards.py`.
- Tests: marker `live`, `make test-live`, `tests/live/conftest.py` (`live_settings`, `require_keys`), `tests/security/planted.py` (`PLANTED_*`, `planted_settings`, `assert_no_planted_key`, `@leak_surface`), `tests/factories.py` (`make_settings`, `loopback_client`, `FakeEnvironment`, `NEPALI`, `NEUTRAL`, `PACK`), `scripts/third_party_licences.py`.
- CI check names: `hygiene`, `api` (gate), `api (ubuntu-latest)`, `api (macos-latest)`, `web`, `contract`, `audit`; required: `hygiene`, `api`, `web`, `contract`, `audit`.

## Cross-phase assumptions

- **Phase 0c** provides a way to read recorded usage per period (the `UsageLedger` totals) so `check_readiness` can fill `UsageSnapshot`; it calls `make_private_file` for recordings and writes its tables through new migrations numbered after `0003`.
- **Phase 0d** produces `CapabilityFindings` from `provider_capabilities` (n-best, prosody, probe date), replaces the platform-order transcriber resolution in `domain/readiness.py` with its speed-aware selection, implements `doctor --probe` (removing the exit-2 stub), registers the `local_models` marker, and appends `@leak_surface` producers for adapter error paths. It keeps the adapter-import rule (only raw adapters import provider SDKs).
- **Phase 0e** assumes pack priors flow through `LanguagePack.prior_for` and that `pack_id` is on profile rows; its extraction stamps observations without needing the pack.
- **Phase 6** assumes `Settings.app_origins` validation and `RequestGuardMiddleware` are the single places token mode relaxes (origins) or extends (Bearer check).

## Open questions for the owner

1. Should the owner enable GitHub private vulnerability reporting (Task 1, Step 5)? `SECURITY.md` points to it.
2. Secrets shorter than 8 characters are not scrubbed from logs. Acceptable, or should the settings validator reject shorter keys instead?
