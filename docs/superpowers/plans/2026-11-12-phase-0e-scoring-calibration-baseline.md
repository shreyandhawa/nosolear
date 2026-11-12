# Phase 0e: Scoring, Calibration and Baseline: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn stored provider results into scored observations under versioned scoring configs, calibrate the detectors on the user's own voice, re-score history without provider calls, and run the baseline through to a report. Together these let a first run work end to end through the API and the CLI.

**Architecture:** Every decision is a pure domain function: the scoring configs and their `v0` rules, extraction (raw results + item + scoring config + pack → observations), the calibration rule, skill scores, the baseline report and the onboarding step. One migration adds the §7 tables and columns that 0e owns. Use cases plug into 0c's job registry: an `extract` step on analyze jobs, plus `calibrate` and `rescore` job kinds. They read 0d's decoded provider results. Routes and CLI commands map HTTP and the terminal onto the use cases.

**Tech Stack:** Python 3.14, FastAPI 0.162.4, SQLAlchemy 2.1.8, Alembic 1.20.1, pytest 9.2.0, Hypothesis 6.170.15, httpx (made a runtime dependency by 0c). **0e adds no dependencies.**

**Spec:** [docs/ARCHITECTURE.md](../../ARCHITECTURE.md): §6 in full (especially §6.2, §6.3, §6.8 and §6.9), §7, §8.1, §9, §11, §12, §13 (Phase 0e) and §15.

## Global Constraints

- **Python and tooling:**
  - Python 3.14 with uv and `uv.lock`.
  - Any new dependency gets an exact pin (`==`) and a lockfile update. This phase needs none.
  - Heavy local-model dependencies go only in the `local` and `apple` extras, and adapters import them lazily.
- **Commands:**
  - From `apps/api`: `uv run pytest -q`, `uv run ruff check`, `uv run ruff format --check`, `uv run pyright` (strict for `src`).
  - From the repo root: `make test`, `make lint`, `make gen-api`.
- **TDD for every change:** write the failing test, run it, write the minimal code, run it again, commit.
- **Layering:**
  - `domain` has no I/O and is deterministic given its inputs.
  - Only `api/deps.py` (and `cli.py` through it) chooses adapters and persistence.
  - Every port has a fake for tests, in `tests/`, following the style of `tests/factories.py`.
- **Property tests:** Hypothesis for domain logic, with the existing profiles: `default` (100 examples) and `heavy` (1000), chosen via `HYPOTHESIS_PROFILE`.
- **Live tests:** tests that call real services are marked `@pytest.mark.live`, are excluded by default and run through `make test-live`. CI never has keys.
- **No real voices or data in the repo:**
  - Never commit audio or anything under `data/`.
  - Test WAVs are generated at test time into `tmp_path` with the stdlib `wave` module, and contain synthetic noise, never a voice.
  - `scripts/check-no-personal-data.sh` runs in CI and in pre-commit.
- **`apps/web`:** the only permitted change is running `make gen-api` after an OpenAPI change and committing the regenerated files.
- **Security (the owner's rules, verbatim):** Keys come only from env or .env. They never appear in logs, API responses, error messages, OpenAPI examples or fixtures. Bind to 127.0.0.1 by default, restrict CORS to the app's origin, and never expose the API unauthenticated. Uploads: cap size and duration, validate the WAV format, generate filenames server-side, write only under the data directory. Treat transcripts and coach output as untrusted. Use structured outputs with the taxonomy enum, and never let model output reach a file path, shell command or SQL string. Check the usage ledger before every paid or quota-limited call, so a bug can't burn a user's quota. Pin and lock dependencies, pin model downloads to a revision, and add a dependency audit to CI. No telemetry. Document exactly what is sent to which provider.
- **Git:**
  - One branch and one PR per task. Name branches `p0e/NN-<slug>`, cut from an up-to-date `origin/main`.
  - Commit and push as you go (`git push -u origin <branch>`).
  - Commit messages are imperative sentences, with **no Co-Authored-By trailer and no "Generated with Claude Code" footer**.
  - Never push to `main`.
  - Squash-merge only when CI is green: `gh pr merge --squash`, **without `--delete-branch`**.
- **HANDOFF.md:** every task's PR updates `docs/superpowers/HANDOFF.md` with what is done, in progress and next, and the list of adapters still unverified against the live service.
- **Scoring values (§6.8; this phase decides them):**
  - `V0_THRESHOLDS`: `nbest_margin=30.0`, `low_accuracy=40.0`, `slow_start_ms=3000`, `long_pause_ms=2000`.
  - `CALIBRATED_THRESHOLDS`: `nbest_margin=15.0`, `low_accuracy=60.0`, `slow_start_ms=3000`, `long_pause_ms=2000`.
  - `nbest_margin` is the top n-best candidate's score minus the expected phone's n-best score, on Azure's 0–100 scale. The expected phone scores 0 when it is absent from the list.
  - A phoneme is weak when its accuracy is below `low_accuracy` and it has no clear substitute.
- **`v0` rules:**
  - `azure_pa` scores `sound.sub.*`, `sound.low.*` and `prosody.*`, and those observations are provisional.
  - The phone probe is drill-only, so `phone_probe` scores nothing.
  - `asr_metrics` scores `fluency.*` and `coach` scores `grammar.*`, `structure.*` and `clarity.*`. These are never provisional.
  - `prosody.word_stress` has no detector and is never scored.
- **Calibration rule (§9.2):**
  - A detector is enabled for a key only with at least 5 error tokens, at least 5 TTS controls, `5·hits ≥ 4·errors` and `5·false_alarms ≤ controls`. Integer arithmetic, so there is no float edge.
  - Attempted-correct takes never enter the rule; they only produce warnings.
  - Each run calibrates sound keys only. **Prosody keys are not calibrated in 0e**, so they stay provisional (decided here and recorded in §9.2 and §18).
- **Provisional (§6.3, §6.8):**
  - An observation is provisional exactly when a sound or prosody family rule scored it. Every `v0` rule is a family rule, and so is the rule any key falls back to when calibration didn't cover it. A key rule written by calibration is never provisional.
  - A profile entry is provisional if any observation it uses is provisional.
- **Deliberate errors never reach the profile.** Attempts with step `calibration` yield no observations, whether in an analyze job or in a re-score.
- **Fluency:**
  - The slow-start miss threshold is 3000 ms; the 5 s on-screen limit belongs to the UI.
  - The long-pause threshold is 2000 ms.
  - Fillers: `{"um", "uh", "uhm", "er", "erm", "ah", "hmm", "mm"}`.
- **Ids:** the `v0` scoring config's id is the literal `"v0"`. Every other new id is `uuid4().hex`. Seed content ids come from the content files.
- **Versions:** `TAXONOMY_VERSION` and `ALGO_VERSION` stay unchanged. The scoring rules JSON carries `"schema": 1`. `BASELINE_PROTOCOL_VERSION = 1`.

## Review Focus

These are the inputs and failure modes most likely to bite a user that no task's ordinary tests would reach. Each has a pinned test in the task that owns the code.

1. **Deliberate calibration errors leaking into the profile.** A token of "vest" said as "west" must never count as the user's v/w error, whether in the analyze job or in a later re-score. Tested in:
   - Task 4: `test_calibration_attempts_yield_nothing`.
   - Task 5: `test_calibration_attempts_write_no_observations` and `test_rescore_skips_calibration_attempts`.
2. **A newer config that scores an attempt with zero observations.** If the newer config writes nothing for that attempt (all its keys were disabled), the profile must stop using the old `v0` observations, not fall back to them. Tested in Task 1 (`test_newer_config_with_no_observations_still_wins`) and Task 2 (`test_current_drops_older_config_even_when_newer_wrote_nothing`).
3. **An Azure resource without n-best or prosody.** It must produce no substitution or prosody observations at all. "ok" rows without evidence would drive miss rates toward "mastered". Calibration must then leave `azure_pa` uncovered for substitution keys. Tested in:
   - Task 3: `test_no_nbest_means_no_substitution_opportunities` and `test_prosody_only_when_returned`.
   - Task 7: `test_no_nbest_means_no_trial_counted`.
4. **A partial or interrupted calibration:** skipped words, or the Azure cap reached while controls are being analyzed. Fewer than 5 + 5 trials must never enable a detector. A cap hit leaves the run `running` and resumable; it is never marked `done` with half the controls. Tested in:
   - Task 7: `test_too_few_trials_never_enable`.
   - Task 8: `test_cap_exceeded_during_controls_keeps_run_running` and `test_controls_are_synthesized_and_scored_once_per_run`.
5. **Calibrating after the baseline.** Once the re-score finishes, the baseline report must show the re-scored observations, with provisional flags cleared for calibrated keys, not the stale snapshot. Tested in Task 10 (`test_rescore_refreshes_completed_baseline_report`) and Task 11 (`test_skip_then_calibrate_later_rescores_without_provider_calls`).

## Not in This Plan

- **`provisional` on `GET /api/profile`.** Adding a required field to `ProfileEntryOut` breaks the web test fixture, and `apps/web` can't change before Phase 2. The baseline report carries the flag instead.
- **Prosody calibration items, and calibration items for `sound.low.*` and `sound.del.final_cluster`.** These keys stay provisional, or drilled but not scored, until a later content PR adds items for them.
- **The daily plan and feedback (Phase 1), the web UI (Phase 2), word stress (Phase 3) and the weekly re-test (Phase 5).**

## File Structure

```
content/
  calibration/items.json                    shared calibration set (converted from 0b's port, extended to ≥5 words per key)
  baseline/protocol.json                    baseline protocol v1: passage A, word list, free talk, rapid questions, articulate
apps/api/src/nosolear/
  domain/attempts.py                        SessionKind, AttemptStep (adds `calibration`)
  domain/scoring.py                         Thresholds, rules, ScoringConfig, V0_CONFIG, rules JSON, current_observations
  domain/observations.py                    + scoring_config_id, provisional
  domain/profile.py                         + ProfileEntry.provisional
  domain/extraction/phones.py               Azure en-US vowel set, s-cluster and final-cluster tests
  domain/extraction/opportunities.py        Opportunity, tracked_keys
  domain/extraction/sounds.py               azure_pa and phone_probe opportunities
  domain/extraction/fluency.py              sentences, fluency opportunities
  domain/extraction/coach.py                coach-issue validation and opportunities
  domain/extraction/extract.py              ExtractionItem, ProviderResults, extract()
  domain/content.py                         content items, calibration set, baseline protocol, validation, copy
  domain/calibration.py                     trials, tally, rule, plan, flagged(), calibrated config
  domain/skill_scores.py                    per-skill composite scores
  domain/baseline_report.py                 the ranked baseline report
  domain/onboarding.py                      next onboarding step
  ports/scoring_stores.py                   ScoringConfigReader/Writer, ExtractionWriter, ExtractionInputs
  ports/content_store.py, ports/calibration_store.py, ports/baseline_store.py
  adapters/content_files.py                 reads content/ JSON into domain types
  persistence/models.py                     + 0e tables and columns
  persistence/migrations/versions/0006_scoring_calibration.py
  persistence/scoring_repository.py         ScoringConfigRepository, ExtractionRepository, ExtractionInputsRepository
  persistence/content_repository.py, persistence/calibration_repository.py, persistence/baseline_repository.py
  app/extract_attempt.py, app/rescore.py, app/scoring_steps.py
  app/calibrate.py, app/calibrate_job.py
  app/baseline.py, app/onboarding.py
  api/rescore_routes.py
  api/calibration_routes.py, api/calibration_schemas.py
  api/baseline_routes.py, api/baseline_schemas.py
  api/onboarding_routes.py, api/onboarding_schemas.py
  first_run_cli.py                          rescore, calibrate, baseline, onboarding, stand-in commands
apps/api/tests/
  strategies.py                             Hypothesis strategies for configs and provider results
  oracle_voice.py                           scripted fakes: synthesizer, scorer, transcriber
  harness.py                                app + fakes + job drain, for API, CLI and e2e tests
  e2e/test_first_run.py
  live/test_first_run_live.py
```

---

### Task 1: Scoring configs, provisional observations and the newest-config rule

**Files:**
- Create: `apps/api/src/nosolear/domain/scoring.py`, `apps/api/tests/strategies.py`
- Modify:
  - `domain/observations.py`: two new fields.
  - `domain/profile.py`: `ProfileEntry.provisional`.
  - `dev/seed.py`: stamp observations with `v0`.
  - `tests/factories.py`: `mk` gains `attempt_id`, `scoring_config_id` and `provisional` keyword arguments.
- Test: `tests/domain/test_scoring.py`, `tests/domain/test_scoring_properties.py`, `tests/domain/test_profile.py` (two tests added)

**Interfaces:**
- **Consumes:** `Detector`, `Family`, `KeyDefinition` and `Taxonomy` (0a); `Observation` and `make_observation` (0a); `build_profile(..., pack=...)` (0b).
- **Produces, in `domain/scoring.py`:**
  - `V0_CONFIG_ID = "v0"`.
  - `class ConfigKind(StrEnum)`: `V0 = "v0"`, `CALIBRATED = "calibrated"`.
  - `@dataclass(frozen=True, slots=True) class Thresholds`: `nbest_margin: float`, `low_accuracy: float`, `slow_start_ms: int`, `long_pause_ms: int`. Plus `V0_THRESHOLDS` and `CALIBRATED_THRESHOLDS`, with the values from Global Constraints.
  - `SOUND_FAMILIES: frozenset[Family]`: SUB, LOW, INS, DEL and PROSODY.
  - `FamilyRule(detector: Detector, family: Family, enabled: bool, provisional: bool)`.
  - `TrialCounts(errors: int, hits: int, controls: int, false_alarms: int, correct_takes: int, correct_flags: int)`.
  - `KeyRule(detector: Detector, error_key: str, enabled: bool, thresholds: Thresholds, counts: TrialCounts)`.
  - `ScoringRule(provisional: bool, thresholds: Thresholds)`.
  - `ScoringConfig(id: str, kind: ConfigKind, calibration_run_id: str | None, thresholds: Thresholds, family_rules: tuple[FamilyRule, ...], key_rules: tuple[KeyRule, ...])`, with the method `rule_for(detector: Detector, definition: KeyDefinition) -> ScoringRule | None` (`None` means disabled).
  - `V0_FAMILY_RULES` and `V0_CONFIG`.
  - `class ScoringConfigInvalid(ValueError)`.
  - `rules_to_json(config: ScoringConfig) -> dict[str, object]`.
  - `rules_from_json(*, config_id: str, kind: ConfigKind, calibration_run_id: str | None, rules: Mapping[str, object], taxonomy: Taxonomy) -> ScoringConfig`.
  - `canonical_json(value: object) -> str`: `json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`.
  - `enabled_keys(config: ScoringConfig, detector: Detector, keys: Iterable[str], taxonomy: Taxonomy) -> frozenset[str]`.
  - `current_observations(observations: Iterable[Observation], *, scored: Iterable[tuple[str, str]], config_order: Sequence[str]) -> list[Observation]`. `scored` holds `(attempt_id, scoring_config_id)` pairs that extraction has written; `config_order` runs oldest to newest.
- **Produces, elsewhere:**
  - `Observation` gains `scoring_config_id: str = V0_CONFIG_ID` and `provisional: bool = False`, after `evidence`.
  - `make_observation(..., scoring_config_id: str = V0_CONFIG_ID, provisional: bool = False)`.
  - `ProfileEntry.provisional: bool`, which `build_profile` sets.

**`rule_for`, checked in order:**
1. If the detector is not in `definition.detectors`, return `None`.
2. If there is a key rule for (detector, key), return `ScoringRule(False, rule.thresholds)` when it is enabled, otherwise `None`.
3. If the family rule for (detector, family) is enabled, return `ScoringRule(rule.provisional, config.thresholds)`.
4. Otherwise return `None`.

**`__post_init__` checks:** `kind is V0` ⇔ `calibration_run_id is None`, and there are no duplicate family or key rules. Either failure raises `ScoringConfigInvalid`.

**`rules_from_json` checks:**
- `schema == 1`.
- Every key-rule key is in the taxonomy, and its detector is allowed for it.
- Every number is finite.
- Counts are non-negative integers, with `hits ≤ errors`, `false_alarms ≤ controls` and `correct_flags ≤ correct_takes`.

Any failure raises `ScoringConfigInvalid`. Rules are serialized sorted: family rules by (detector, family), key rules by (error_key, detector).

**`current_observations`:**
- For each attempt with at least one `scored` pair, keep only its observations whose config is the newest of those pairs in `config_order`.
- Keep every observation of an attempt with no pairs, and every observation with `attempt_id is None`.
- Preserve the input order.

- [ ] **Step 1: Write the failing tests**

```python
# tests/domain/test_scoring.py
V0_RULES_JSON = {
    "schema": 1,
    "thresholds": {"nbest_margin": 30.0, "low_accuracy": 40.0, "slow_start_ms": 3000, "long_pause_ms": 2000},
    "family_rules": [
        {"detector": "asr_metrics", "family": "fluency", "enabled": True, "provisional": False},
        {"detector": "azure_pa", "family": "prosody", "enabled": True, "provisional": True},
        {"detector": "azure_pa", "family": "sound.low", "enabled": True, "provisional": True},
        {"detector": "azure_pa", "family": "sound.sub", "enabled": True, "provisional": True},
        {"detector": "coach", "family": "clarity", "enabled": True, "provisional": False},
        {"detector": "coach", "family": "grammar", "enabled": True, "provisional": False},
        {"detector": "coach", "family": "structure", "enabled": True, "provisional": False},
        {"detector": "phone_probe", "family": "sound.del", "enabled": False, "provisional": True},
        {"detector": "phone_probe", "family": "sound.ins", "enabled": False, "provisional": True},
        {"detector": "phone_probe", "family": "sound.sub", "enabled": False, "provisional": True},
    ],
    "key_rules": [],
}

def test_v0_rules_json_is_pinned():
    assert rules_to_json(V0_CONFIG) == V0_RULES_JSON

V0 = ScoringRule(provisional=True, thresholds=V0_THRESHOLDS)
FIRM = ScoringRule(provisional=False, thresholds=V0_THRESHOLDS)

@pytest.mark.parametrize("key, detector, expected", [
    ("sound.sub.v.w", Detector.AZURE_PA, V0), ("sound.sub.p.b", Detector.AZURE_PA, V0),
    ("sound.low.θ", Detector.AZURE_PA, V0), ("prosody.monotone", Detector.AZURE_PA, V0),
    ("sound.sub.v.w", Detector.PHONE_PROBE, None), ("sound.ins.epenthesis_sC", Detector.PHONE_PROBE, None),
    ("sound.del.final_cluster", Detector.AZURE_PA, None), ("prosody.word_stress", Detector.AZURE_PA, None),
    ("fluency.filler", Detector.ASR_METRICS, FIRM), ("grammar.article", Detector.COACH, FIRM),
])
def test_v0_rule_table(key, detector, expected):
    assert V0_CONFIG.rule_for(detector, TAX.get(key)) == expected

def test_v0_is_stricter_than_calibrated():
    assert V0_THRESHOLDS.nbest_margin > CALIBRATED_THRESHOLDS.nbest_margin
    assert V0_THRESHOLDS.low_accuracy < CALIBRATED_THRESHOLDS.low_accuracy

def test_key_rule_overrides_family_rule_and_is_never_provisional():
    c = calibrated(key_rules=(KeyRule(Detector.AZURE_PA, "sound.sub.v.w", True, CALIBRATED_THRESHOLDS, COUNTS),
                              KeyRule(Detector.AZURE_PA, "sound.sub.f.p", False, CALIBRATED_THRESHOLDS, COUNTS)))
    assert c.rule_for(Detector.AZURE_PA, TAX.get("sound.sub.v.w")) == ScoringRule(False, CALIBRATED_THRESHOLDS)
    assert c.rule_for(Detector.AZURE_PA, TAX.get("sound.sub.f.p")) is None
    assert c.rule_for(Detector.AZURE_PA, TAX.get("sound.sub.θ.t")) == V0   # uncovered: v0 rule, provisional

@pytest.mark.parametrize("bad", [{"schema": 2}, key_rule_json(error_key="grammar.artcle"),
                                 key_rule_json(detector="coach"), key_rule_json(hits=11, errors=10),
                                 key_rule_json(nbest_margin=float("nan"))])
def test_rules_from_json_rejects_bad_rules(bad):
    with pytest.raises(ScoringConfigInvalid):
        rules_from_json(config_id="c", kind=ConfigKind.CALIBRATED, calibration_run_id="r", rules=bad, taxonomy=TAX)

def test_kind_and_run_id_must_agree():
    with pytest.raises(ScoringConfigInvalid):
        replace(V0_CONFIG, calibration_run_id="r")

def test_keeps_only_the_newest_config_that_scored_each_attempt():
    a1_v0, a1_c1 = mk(K, MISS, T0, attempt_id="a1"), mk(K, OK, T0, attempt_id="a1", scoring_config_id="c1")
    a2_v0, free = mk(K, MISS, T0, attempt_id="a2"), mk(K, MISS, T0)
    kept = current_observations([a1_v0, a1_c1, a2_v0, free],
                                scored=[("a1", "v0"), ("a1", "c1"), ("a2", "v0")], config_order=["v0", "c1"])
    assert kept == [a1_c1, a2_v0, free]

def test_newer_config_with_no_observations_still_wins():
    assert current_observations([mk(K, MISS, T0, attempt_id="a1")],
                                scored=[("a1", "v0"), ("a1", "c1")], config_order=["v0", "c1"]) == []
```

```python
# tests/domain/test_profile.py (added)
def test_entry_is_provisional_if_any_used_observation_is():
    obs = [mk("sound.sub.v.w", MISS, T0, provisional=True), mk("sound.sub.v.w", OK, T0)]
    assert build_profile(obs, as_of=T0, taxonomy=TAX, pack=PACK).entries[0].provisional

def test_entry_is_firm_when_no_observation_is_provisional():
    obs = [mk("fluency.filler", MISS, T0, detector=Detector.ASR_METRICS)]
    assert not build_profile(obs, as_of=T0, taxonomy=TAX, pack=PACK).entries[0].provisional
```

```python
# tests/domain/test_scoring_properties.py  (strategies in tests/strategies.py: scoring_configs(),
# sound_keys(), detectors(), observation lists with attempt ids "a0".."a4" and configs "v0","c1","c2")
@given(config=scoring_configs(), key=all_keys(), detector=detectors())
def test_rule_for_follows_key_rules_then_family_rules(config, key, detector): ...
    # detector not allowed -> None; a key rule decides alone (never provisional); else the family rule

@given(key=all_keys(), detector=detectors())
def test_v0_provisional_exactly_for_sound_and_prosody(key, detector): ...
    # rule = V0_CONFIG.rule_for(...); if rule: rule.provisional == (TAX.get(key).family in SOUND_FAMILIES)
    # phone_probe -> always None

@given(config=scoring_configs())
def test_rules_json_round_trip(config): ...
    # rules_from_json(rules_to_json(c)) == c, and canonical_json(...) is stable across two calls

@given(obs=attempt_observations(), scored=scored_pairs())
def test_current_observations_keeps_one_config_per_attempt(obs, scored): ...
    # every kept attempt's observations share one config: the newest of its scored pairs;
    # attempt-less observations are all kept; result is a sub-sequence of the input
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `cd apps/api && uv run pytest tests/domain -q`
Expected: FAIL (`ModuleNotFoundError: nosolear.domain.scoring`).

- [ ] **Step 3: Implement `domain/scoring.py` and the field changes**

Follow the Interfaces block and the rules above. `build_profile` sets `provisional = any(o.provisional for o in group)` over the observations it includes for the key. `dev/seed.py` passes `provisional=V0_CONFIG.rule_for(detector, defn) is not None and defn.family in SOUND_FAMILIES`, so seeded sound keys look like what `v0` would produce.

- [ ] **Step 4: Run the tests and lint, and confirm they pass**

Run: `uv run pytest -q && uv run pyright && uv run ruff check`
Expected: all pass (0a's tests unchanged, because both new fields have defaults).

- [ ] **Step 5: Commit, open the PR, merge when green**

```bash
git fetch origin && git switch -c p0e/01-scoring-configs origin/main
git add apps/api docs/superpowers/HANDOFF.md
git commit -m "Add scoring configs with v0 rules and provisional observations"
git push -u origin p0e/01-scoring-configs && gh pr create --fill
gh pr checks --watch && gh pr merge --squash
```

---

### Task 2: Scoring schema migration and repositories

**Files:**
- Create:
  - `apps/api/src/nosolear/domain/attempts.py`
  - `apps/api/src/nosolear/persistence/migrations/versions/0006_scoring_calibration.py`
  - `apps/api/src/nosolear/persistence/scoring_repository.py`
  - `apps/api/src/nosolear/ports/scoring_stores.py`
- Modify:
  - `persistence/models.py`
  - `persistence/repositories.py` (`ObservationRepository`, `ProfileRepository`)
  - `ports/stores.py` (`ObservationReader.current`)
  - `app/rebuild_profile.py` (reads `current()`)
  - `docs/ARCHITECTURE.md`: §6.8 `v0` values; §7 the `extractions` table and the `calibrate` job kind; §18 `v0` decided.
- Test: `tests/persistence/test_schema.py`, `tests/persistence/test_scoring_repository.py`, `tests/persistence/test_repositories.py`, `tests/app/test_rebuild_profile.py`

**Interfaces:**
- **Consumes:**
  - Task 1: `ScoringConfig`, `V0_CONFIG`, `rules_to_json`, `rules_from_json`, `canonical_json` and `current_observations`.
  - 0c's tables `recordings`, `jobs` and `analyses`, and 0d's `tts_cache` (see Cross-phase assumptions).
- **Produces:**
  - `domain/attempts.py`:
    - `class SessionKind(StrEnum)`: baseline, daily, retest, conversation and `CALIBRATION = "calibration"`.
    - `class AttemptStep(StrEnum)`: the eight 0a steps plus `CALIBRATION = "calibration"`.
    - `models.ATTEMPT_STEPS = tuple(AttemptStep)`.
  - **Schema (§7 plus one table):**
    - **`scoring_configs`:**
      - Columns `id TEXT PK`, `kind`, `calibration_run_id NULL FK`, `rules_json`, `capabilities_json`, `created_at`.
      - CHECK `kind IN ('v0','calibrated')` and `(kind = 'v0') = (calibration_run_id IS NULL)`.
    - **`calibration_runs`:**
      - Columns `id TEXT PK`, `session_id NULL FK sessions`, `status`, `scoring_config_id NULL FK`, `started_at`, `completed_at NULL`.
      - CHECK `status IN ('running','done','skipped')`.
    - **`calibration_trials`:**
      - Columns `id INTEGER PK`, `run_id FK`, `error_key`, `detector`, `kind`, `attempt_id NULL FK`, `tts_hash NULL FK tts_cache.hash`, `flagged BOOLEAN NULL`, `evidence_json`.
      - CHECK `kind IN ('error','control')`, `(attempt_id IS NULL) <> (tts_hash IS NULL)` and `kind = 'control' OR attempt_id IS NOT NULL`.
      - Unique `(run_id, error_key, detector, attempt_id)` and `(run_id, error_key, detector, tts_hash)`.
      - A control row with an `attempt_id` is an attempted-correct take; one with a `tts_hash` is a TTS control.
    - **`content_items`:**
      - Columns `id TEXT PK`, `kind`, `text`, `target_keys` (a JSON array), `source`, `retired_at NULL`.
      - CHECK `kind` is one of the seven §7 kinds, and `source IN ('seed','coach')`.
    - **`skill_scores`:**
      - Columns `session_id FK`, `skill`, `score`, `components_json`; PK `(session_id, skill)`.
      - CHECK the skill is one of the three, and `score BETWEEN 0 AND 100`.
    - **`extractions` (new, not yet in §7):**
      - Columns `attempt_id FK`, `scoring_config_id FK`, `detector`, `observation_count`, `created_at`; PK `(attempt_id, scoring_config_id, detector)`.
      - One row per detector whose observations extraction has written for an attempt under a config, even when it wrote none.
    - **`observations`:** adds `scoring_config_id TEXT NOT NULL FK` and `provisional BOOLEAN NOT NULL`.
    - **`profile_entries`:** adds `provisional BOOLEAN NOT NULL` with server default false.
    - **`sessions.kind`** CHECK adds `calibration`.
    - **`attempts`:** the `step` CHECK adds `calibration`, plus a new `content_item_id NULL FK content_items`.
    - **`analyses`:**
      - `attempt_id` becomes nullable; adds `tts_hash NULL FK tts_cache.hash` and `calibration_run_id NULL FK`.
      - CHECK `(attempt_id IS NULL) <> (tts_hash IS NULL)` and `(tts_hash IS NULL) = (calibration_run_id IS NULL)`.
      - Unique `(tts_hash, kind, calibration_run_id)`.
    - **`jobs.kind`** CHECK adds `calibrate`.
  - **`ports/scoring_stores.py`:**
    - `ScoringConfigReader`: `newest() -> ScoringConfig` and `get(config_id: str) -> ScoringConfig`.
    - `ScoringConfigWriter`: `add(config: ScoringConfig, *, capabilities: Mapping[str, object], created_at: datetime) -> None`.
    - `ExtractionWriter`: `write(*, attempt_id: str, scoring_config_id: str, detector: Detector, observations: Sequence[Observation], created_at: datetime) -> bool`.
  - **`persistence/scoring_repository.py`:**
    - `ScoringConfigRepository(engine, taxonomy)` implements both config ports, plus `order() -> list[str]`: `v0` first, then calibrated configs by `(created_at, id)`. `newest()` is the last entry.
    - `ExtractionRepository(engine)`:
      - `write` inserts the marker and the observations in one transaction. It returns `False`, writing nothing, when the marker already exists, including on the `IntegrityError` of a concurrent writer.
      - `scored() -> list[tuple[str, str]]`.
  - **`ObservationRepository`:**
    - `add_many` and `all` carry `scoring_config_id` and `provisional`.
    - `current() -> list[Observation]` applies `current_observations` with `ExtractionRepository.scored()` and `ScoringConfigRepository.order()`.
  - **`ProfileRepository`:**
    - Saves `provisional` in `profile_entries` and in every snapshot entry; `latest()` restores it.
    - `rebuild_profile` reads `observations.current()`.

**Migration `0006`** (`down_revision` = the head left by 0d, assumed `"0005"`; if the head differs, use the next free number and that head). Steps, in order:
1. `PRAGMA defer_foreign_keys=ON`.
2. Create `content_items`, `calibration_runs`, `scoring_configs`, `calibration_trials`, `skill_scores` and `extractions`. SQLite checks the mutual foreign keys between runs and configs on writes, not on CREATE.
3. Insert the `v0` row:
   - `id='v0'`, `kind='v0'`, `calibration_run_id=NULL`, `capabilities_json='{}'`, `created_at` = the time the migration runs.
   - `rules_json` = the literal string `canonical_json(V0_RULES_JSON)`. Copy it in; don't import it from `domain`, because a migration is frozen at the time it was written.
4. Batch-alter the existing tables as listed above. Backfill observations with `scoring_config_id='v0'`, and set `provisional = (error_key LIKE 'sound.%' OR error_key LIKE 'prosody.%')`.
5. Insert one `extractions` row for each distinct `(attempt_id, 'v0', detector)` among existing observations that have an attempt.

`downgrade()` reverses each step.

- [ ] **Step 1: Write the failing tests**

```python
# tests/persistence/test_schema.py (added; the existing drift test must keep passing)
def test_v0_row_matches_code(db_engine):
    with db_engine.connect() as c:
        row = c.execute(text("SELECT kind, calibration_run_id, rules_json FROM scoring_configs WHERE id='v0'")).one()
    assert row == ("v0", None, canonical_json(rules_to_json(V0_CONFIG)))

@pytest.mark.parametrize("table, column, good, bad", [
    ("sessions", "kind", "calibration", "calib"), ("attempts", "step", "calibration", "cal"),
    ("calibration_runs", "status", "skipped", "aborted"), ("calibration_trials", "kind", "control", "ctrl"),
    ("content_items", "kind", "calibration_word", "word"), ("skill_scores", "skill", "articulate", "speaking"),
    ("extractions", "detector", "azure_pa", "whisper"),
])
def test_new_enum_checks(conn, table, column, good, bad): ...   # insert with good succeeds, bad raises IntegrityError

def test_trial_needs_exactly_one_subject(conn): ...        # both or neither of attempt_id/tts_hash -> IntegrityError
def test_error_trial_needs_an_attempt(conn): ...           # kind='error' with tts_hash only -> IntegrityError
def test_analysis_needs_exactly_one_subject(conn): ...     # control row without calibration_run_id -> IntegrityError
def test_skill_score_range(conn): ...                       # 100.5 -> IntegrityError

def test_migration_0006_backfills_existing_observations(tmp_path):
    engine = create_engine_for(f"sqlite:///{tmp_path / 'm.sqlite'}")
    upgrade_to_head(engine, revision=PREVIOUS_HEAD)          # "0005"
    insert_session_attempt_and_observations(engine, keys=["sound.sub.v.w", "fluency.filler"], attempt_id="a")
    upgrade_to_head(engine)
    rows = query(engine, "SELECT error_key, scoring_config_id, provisional FROM observations ORDER BY error_key")
    assert rows == [("fluency.filler", "v0", 0), ("sound.sub.v.w", "v0", 1)]
    assert query(engine, "SELECT attempt_id, scoring_config_id FROM extractions") == [("a", "v0"), ("a", "v0")]
```

```python
# tests/persistence/test_scoring_repository.py
def test_v0_is_oldest_and_newest_until_calibrated(db_engine):
    repo = ScoringConfigRepository(db_engine, TAX)
    assert repo.newest() == V0_CONFIG and repo.order() == ["v0"]
    repo.add(CAL_CONFIG, capabilities={"azure_pa": {"nbest": True}}, created_at=T0)
    assert repo.newest() == CAL_CONFIG and repo.order() == ["v0", CAL_CONFIG.id]
    assert repo.get(CAL_CONFIG.id) == CAL_CONFIG

def test_write_is_once_per_attempt_config_and_detector(db_engine):
    ex = ExtractionRepository(db_engine)
    assert ex.write(attempt_id="a", scoring_config_id="v0", detector=Detector.AZURE_PA, observations=[OBS], created_at=T0)
    assert not ex.write(attempt_id="a", scoring_config_id="v0", detector=Detector.AZURE_PA, observations=[OBS], created_at=T0)
    assert count(db_engine, "observations") == 1

def test_current_drops_older_config_even_when_newer_wrote_nothing(db_engine):
    write(attempt="a", config="v0", observations=[OBS_A_V0]); add(CAL_CONFIG)
    write(attempt="a", config=CAL_CONFIG.id, observations=[])
    assert ObservationRepository(db_engine).current() == []
    assert len(ObservationRepository(db_engine).all()) == 1      # append-only: nothing deleted

def test_observation_roundtrip_keeps_config_and_provisional(db_engine): ...
def test_profile_roundtrip_keeps_provisional(db_engine): ...      # latest() == p with a provisional entry; snapshot JSON has "provisional"
```

```python
# tests/app/test_rebuild_profile.py (added)
def test_rebuild_reads_only_current_observations(db_engine): ...
    # v0 miss + calibrated ok for the same attempt -> the profile entry counts only the ok
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `uv run pytest tests/persistence tests/app -q`
Expected: FAIL (no `scoring_configs` table; `ScoringConfigRepository` is not defined).

- [ ] **Step 3: Implement the models, the migration, the repositories and the port changes**

Follow the Interfaces block. In `models.py`, CHECK lists come from the enums (`SessionKind`, `AttemptStep`, `ConfigKind`, `Detector`, `Skill`, `ContentKind` as a string tuple until Task 6) through `_in_list`, as 0a does. Then update `docs/ARCHITECTURE.md`:
- §6.8: one line with the `v0` and calibrated thresholds.
- §7: an `extractions` row with its purpose, plus `calibrate` among the `jobs.kind` values.
- §18: mark "`v0` margins and thresholds" as decided on 2026-11-12.

- [ ] **Step 4: Run the tests and lint, and confirm they pass**

Run: `uv run pytest -q && uv run pyright && uv run ruff check && uv run ruff format --check`
Expected: all pass; `test_models_match_migrations` reports no drift.

- [ ] **Step 5: Commit, open the PR, merge when green**

```bash
git fetch origin && git switch -c p0e/02-scoring-schema origin/main
git add apps/api docs/ARCHITECTURE.md docs/superpowers/HANDOFF.md
git commit -m "Add scoring, calibration and content tables with a v0 scoring config row"
git push -u origin p0e/02-scoring-schema && gh pr create --fill
gh pr checks --watch && gh pr merge --squash
```

---

### Task 3: Sound and prosody extraction

**Files:**
- Create: `apps/api/src/nosolear/domain/extraction/__init__.py`, `phones.py`, `opportunities.py`, `sounds.py`
- Modify: `tests/factories.py` (builders for 0d result types), `tests/strategies.py` (`pronunciation_results()`, `probe_results()`)
- Test: `tests/domain/extraction/test_sounds.py`, `tests/domain/extraction/test_sounds_properties.py`

**Interfaces:**
- **Consumes:**
  - 0d's `PronunciationResult`, `PaWord`, `PaPhoneme`, `PhoneCandidate`, `PhoneProbeResult`, `ProbeWord` and `ProbeOp`. The fields read are listed under Cross-phase assumptions.
  - 0b's `LanguagePack`.
  - `Thresholds` (Task 1).
- **Produces:**
  - `domain/extraction/phones.py`:
    - `AZURE_VOWELS = frozenset({"i", "ɪ", "eɪ", "ɛ", "æ", "ɑ", "ɔ", "ʊ", "oʊ", "u", "ʌ", "ə", "aɪ", "aʊ", "ɔɪ", "ɝ", "ɚ"})`.
    - `is_vowel(phone: str) -> bool`.
    - `starts_with_s_cluster(phones: Sequence[str]) -> bool`: the first phone is `s` and the second is a consonant.
    - `ends_with_consonant_cluster(phones: Sequence[str]) -> bool`: the last two phones are consonants.
  - `domain/extraction/opportunities.py`:
    - `Opportunity(error_key: str, missed: bool, evidence: Mapping[str, object])`.
    - `ThresholdsFor = Callable[[str], Thresholds]`.
    - `tracked_keys(taxonomy: Taxonomy, pack: LanguagePack) -> frozenset[str]`: every defined key, plus the keys the pack names in `hypotheses` and `calibration_emphasis`.
  - `domain/extraction/sounds.py`:
    - `clear_substitute(phoneme: PaPhoneme, margin: float) -> str | None`.
    - `azure_opportunities(result: PronunciationResult, *, keys: frozenset[str], thresholds_for: ThresholdsFor) -> list[Opportunity]`.
    - `probe_opportunities(result: PhoneProbeResult, *, keys: frozenset[str]) -> list[Opportunity]`.
  - Evidence keys: `word`, `start_ms`, `end_ms` (the word's span, for clip playback; `None` when the probe gives no timing), `expected`, `produced`, `score`.

**Opportunity rules (§6.2).** Words whose Azure `error_type` is `"Omission"` or `"Insertion"` are skipped; every other word counts as scored.
- **`clear_substitute`:**
  - Returns `None` if `nbest` is empty.
  - Otherwise it takes the top candidate by `(-score, phone)`. It returns that phone if the phone differs from the expected one and `top.score − expected_score ≥ margin`, else `None`.
- **`sound.sub.<e>.<p>` (azure_pa), only when `result.has_nbest`:** every expected /e/ phoneme in a scored word is one opportunity for each tracked key `sound.sub.e.*`. It is missed when `clear_substitute(phoneme, thresholds_for(key).nbest_margin) == p`.
- **`sound.low.<e>` (azure_pa):** every expected /e/ phoneme in a scored word. It is missed when there is no clear substitute (checked with this key's `nbest_margin`, and treated as none when `has_nbest` is false) and `accuracy < thresholds_for(key).low_accuracy`.
- **Prosody (azure_pa), only when `result.has_prosody`:**
  - `prosody.unexpected_break` and `prosody.missing_break`: every scored word after the first, missed when that word carries the flag.
  - `prosody.monotone`: one opportunity per clip with at least one scored word, missed when any scored word carries `monotone`.
- **`sound.sub.<e>.<p>` (phone_probe):** every op with `expected == e` (match, sub or del) is one opportunity for each tracked key `sound.sub.e.*`, missed when `op.kind == "sub" and op.heard == p`.
- **`sound.ins.epenthesis_sC` (phone_probe):** every probe word whose `expected` starts with an s-cluster, missed when there is an `ins` op at position 0 whose heard phone is a vowel.
- **`sound.del.final_cluster` (phone_probe):** every probe word whose `expected` ends in a consonant cluster, missed when there is a `del` op at position `len(expected) − 1`.

Only keys in `keys` produce opportunities. Output order follows the words, then the phonemes, then the keys sorted.

- [ ] **Step 1: Write the failing tests**

```python
# tests/domain/extraction/test_sounds.py   (builders: pa_phone(phone, acc, nbest=()), pa_word(text, phones, error_type="None", ...),
#                                           pa_result(words, has_nbest=True, has_prosody=True), probe_word(text, expected, ops))
ALL = tracked_keys(TAX, PACK)
def v0(_: str) -> Thresholds: return V0_THRESHOLDS

def test_substitution_needs_a_clear_margin():
    r = pa_result([pa_word("vest", [pa_phone("v", 30, [("w", 80), ("v", 40)]), pa_phone("ɛ", 95), ...])])
    vw = [o for o in azure_opportunities(r, keys=ALL, thresholds_for=v0) if o.error_key == "sound.sub.v.w"]
    assert [o.missed for o in vw] == [True]                                     # margin 40 >= 30
    strict = lambda _: replace(V0_THRESHOLDS, nbest_margin=50.0)
    assert [o.missed for o in azure_opportunities(r, keys=ALL, thresholds_for=strict) if o.error_key == "sound.sub.v.w"] == [False]

def test_every_expected_phone_is_one_opportunity_per_sub_key():
    r = pa_result([pa_word("vivid", [pa_phone("v", 95, [("v", 95)]), ..., pa_phone("v", 95, [("v", 95)]), ...])])
    assert sum(o.error_key == "sound.sub.v.w" for o in azure_opportunities(r, keys=ALL, thresholds_for=v0)) == 2

def test_no_nbest_means_no_substitution_opportunities():
    r = pa_result([pa_word("think", [pa_phone("θ", 20)])], has_nbest=False)
    opps = azure_opportunities(r, keys=ALL, thresholds_for=v0)
    assert not [o for o in opps if o.error_key.startswith("sound.sub.")]
    assert [(o.error_key, o.missed) for o in opps if o.error_key == "sound.low.θ"] == [("sound.low.θ", True)]

def test_weak_sound_only_without_a_clear_substitute():
    r = pa_result([pa_word("think", [pa_phone("θ", 30, [("t", 90), ("θ", 30)])])])
    got = {o.error_key: o.missed for o in azure_opportunities(r, keys=ALL, thresholds_for=v0)}
    assert got["sound.sub.θ.t"] is True and got["sound.low.θ"] is False

def test_omitted_and_inserted_words_are_skipped(): ...
def test_prosody_only_when_returned(): ...            # has_prosody=False -> no prosody.* opportunities
def test_monotone_is_one_opportunity_per_clip(): ...
def test_dynamic_pack_key_is_tracked(): ...           # pack hypothesis "sound.sub.p.b" -> expected /p/ yields it
def test_probe_epenthesis_and_final_cluster():
    w = probe_word("school", ["s", "k", "u", "l"], [ins(0, "ɪ"), match("s"), match("k"), match("u"), match("l")])
    got = {o.error_key: o.missed for o in probe_opportunities(probe_result([w]), keys=ALL)}
    assert got["sound.ins.epenthesis_sC"] is True and "sound.del.final_cluster" not in got
def test_probe_substitution_counts_deleted_phones_as_ok(): ...
def test_evidence_carries_word_span_and_phones(): ...  # {"word": "vest", "start_ms": 100, "end_ms": 520, "expected": "v", "produced": "w", "score": 30}
```

```python
# tests/domain/extraction/test_sounds_properties.py
@given(r=pronunciation_results(has_nbest=True))
def test_sub_opportunities_equal_expected_phone_count(r): ...
    # for every tracked key sound.sub.e.p: count(opps for key) == count(phonemes == e in scored words)

@given(r=pronunciation_results())
def test_a_phoneme_yields_at_most_one_substitution_miss(r): ...
    # for every expected e: sum of misses over keys sound.sub.e.* <= count(phonemes == e in scored words)

@given(r=pronunciation_results(), p=probe_results())
def test_sound_extraction_is_deterministic(r, p): ...
    # same input (and a deep copy of it) -> equal output lists
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `uv run pytest tests/domain/extraction -q`
Expected: FAIL (`ModuleNotFoundError: nosolear.domain.extraction`).

- [ ] **Step 3: Implement `phones.py`, `opportunities.py` and `sounds.py`**

Follow the rules above. Build the `expected phone → [(key, produced)]` index once per call from `keys`, splitting each sub key on its last two dots.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/domain -q && uv run pyright`
Expected: all pass, and Hypothesis finds no falsifying example.

- [ ] **Step 5: Commit, open the PR, merge when green**

```bash
git fetch origin && git switch -c p0e/03-sound-extraction origin/main
git add apps/api docs/superpowers/HANDOFF.md
git commit -m "Extract sound and prosody opportunities from Azure and phone-probe results"
git push -u origin p0e/03-sound-extraction && gh pr create --fill
gh pr checks --watch && gh pr merge --squash
```

---

### Task 4: Fluency and coach extraction, and the `extract` entry point

**Files:**
- Create: `apps/api/src/nosolear/domain/extraction/fluency.py`, `coach.py`, `extract.py`
- Modify: `tests/factories.py` (builders `transcript(...)`, `coach_result(...)`), `tests/strategies.py` (`transcripts()`, `coach_results()`, `provider_results()`)
- Test: `tests/domain/extraction/test_fluency.py`, `test_coach.py`, `test_extract.py`, `test_extract_properties.py`

**Interfaces:**
- **Consumes:** 0d's `Transcript`, `TimedWord`, `CoachResult` and `CoachIssue`; Task 3's `Opportunity`, `tracked_keys`, `azure_opportunities` and `probe_opportunities`; Task 1's `ScoringConfig` and `enabled_keys`; `make_observation`.
- **Produces:**
  - `domain/extraction/fluency.py`:
    - `FILLERS: frozenset[str]` (Global Constraints).
    - `normalize(word: str) -> str`: lowercase, with surrounding punctuation stripped.
    - `sentences(words: Sequence[TimedWord]) -> list[tuple[TimedWord, ...]]`: a sentence ends after a word whose raw text ends in `.`, `?` or `!`, and leftover words form a last sentence.
    - `fluency_opportunities(transcript: Transcript, *, step: str, keys: frozenset[str], thresholds_for: ThresholdsFor) -> list[Opportunity]`.
  - `domain/extraction/coach.py`:
    - `COACH_FAMILIES_BY_STEP: Mapping[str, frozenset[Family]]`: `speak` → {GRAMMAR, CLARITY}, `quick_answer` → {GRAMMAR}, `articulate` → {GRAMMAR, STRUCTURE, CLARITY}.
    - `valid_issues(coach: CoachResult, transcript: Transcript, *, step: str, taxonomy: Taxonomy) -> list[CoachIssue]`.
    - `coach_opportunities(coach: CoachResult, transcript: Transcript, *, step: str, keys: frozenset[str], taxonomy: Taxonomy) -> list[Opportunity]`.
  - `domain/extraction/extract.py`:
    - `ExtractionItem(attempt_id: str, step: str, scripted: bool, observed_at: datetime)`.
    - `ProviderResults(pronunciation: PronunciationResult | None = None, transcript: Transcript | None = None, phone_probe: PhoneProbeResult | None = None, coach: CoachResult | None = None)`.
    - `DETECTOR_INPUT: Mapping[Detector, str]`: `azure_pa` → `"pronunciation"`, `phone_probe` → `"phone_probe"`, `asr_metrics` → `"transcript"`, `coach` → `"coach"`.
    - `extract(item: ExtractionItem, results: ProviderResults, *, config: ScoringConfig, pack: LanguagePack, taxonomy: Taxonomy) -> dict[Detector, tuple[Observation, ...]]`: one entry for every detector whose input is present, even when it holds no observations.

**Fluency rules (`asr_metrics`).** Unscripted steps are `speak`, `quick_answer` and `articulate`; scripted steps yield nothing.
- **`fluency.slow_start`:** one opportunity on a `quick_answer` attempt. It is missed when there are no words or `words[0].start_ms > slow_start_ms`. Evidence: `{"first_word_ms": ...}`.
- **The other three keys:** one opportunity per sentence on each unscripted step.
  - `fluency.filler` is missed when the sentence contains a filler. Its evidence includes `"undercounted": transcript.drops_fillers`.
  - `fluency.long_pause` is missed when a gap between consecutive words exceeds `long_pause_ms`. The gaps counted are those inside the sentence and the one before its first word, except for the first sentence.
  - `fluency.false_start` is missed when the sentence immediately repeats a 1–3 word sequence (normalized, fillers removed), as in "I I think" or "we went we went".
- **Evidence:** the sentence's `start_ms` and `end_ms`, and `text`.

**Coach rules (`coach`).** Coach output is untrusted.
- `valid_issues` drops an issue when any of these holds:
  - its key is not in the taxonomy;
  - `coach` is not an allowed detector for the key;
  - the key's family is not in `COACH_FAMILIES_BY_STEP[step]`;
  - it is a grammar issue without a quote;
  - its quote, normalized (lowercased, whitespace collapsed), is not a substring of the normalized transcript text.

  It never raises on bad input.
- **Grammar keys** (tracked and enabled): one opportunity per sentence. A sentence is missed when a valid issue of that key quotes text that begins inside it, located at the quote's first occurrence in the normalized transcript.
- **Structure and clarity keys** (where the step allows them): one opportunity per answer, missed when there is any valid issue of that key.
- **Evidence:** `quote`, plus the sentence span or the answer span.

**`extract`:**
1. Return `{}` when `item.step == "calibration"`.
2. The context is `SCRIPTED` if `item.scripted`, else `UNSCRIPTED`.
3. For each detector whose input is present:
   - `keys = enabled_keys(config, detector, tracked_keys(taxonomy, pack), taxonomy)`.
   - Compute its opportunities with `thresholds_for = lambda k: config.rule_for(detector, taxonomy.get(k)).thresholds`.
   - Map each one through `make_observation(..., confidence=1.0, attempt_id=item.attempt_id, observed_at=item.observed_at, scoring_config_id=config.id, provisional=rule.provisional)`.
4. Coach opportunities need the transcript. With a coach result but no transcript, the coach entry is `()`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/domain/extraction/test_fluency.py   (transcript(("Well,", 600, 900), ("um", 1000, 1200), ...), drops_fillers=False)
def test_slow_start_is_one_opportunity_per_rapid_question():
    late = transcript(("I", 3400, 3500), ("think", 3500, 3900))
    assert opps(late, step="quick_answer", key="fluency.slow_start") == [True]
    assert opps(late, step="speak", key="fluency.slow_start") == []
def test_no_answer_is_a_slow_start(): ...                       # empty transcript on quick_answer -> [True]
def test_fillers_long_pauses_and_false_starts_per_sentence(): ...
    # "I I went home. Um it was late." -> false_start [True, False], filler [False, True]
def test_scripted_steps_have_no_fluency_opportunities(): ...
def test_filler_evidence_flags_undercounting(): ...              # drops_fillers=True -> evidence["undercounted"] is True
```

```python
# tests/domain/extraction/test_coach.py
TEXT = transcript_from("I go to the market yesterday. It was fun.")
@pytest.mark.parametrize("issue", [
    CoachIssue("grammar.artcle", "the market"),           # unknown key
    CoachIssue("sound.sub.v.w", "market"),                # coach may not report sound keys
    CoachIssue("grammar.verb_tense", "I went"),           # quote not in transcript
    CoachIssue("grammar.verb_tense", None),               # grammar needs a quote
    CoachIssue("structure.missing_point", None),          # structure not judged on quick answers
    CoachIssue("grammar.article'); DROP TABLE observations;--", "x"),
])
def test_coach_output_is_untrusted(issue):
    assert valid_issues(coach_result([issue]), TEXT, step="quick_answer", taxonomy=TAX) == []

def test_grammar_miss_lands_in_the_quoted_sentence():
    c = coach_result([CoachIssue("grammar.verb_tense", "I go to")])
    assert opps(c, TEXT, step="quick_answer", key="grammar.verb_tense") == [True, False]
def test_structure_is_one_opportunity_per_answer(): ...         # articulate, missing_reason -> [True]
```

```python
# tests/domain/extraction/test_extract.py
def test_calibration_attempts_yield_nothing():
    item = ExtractionItem("a", "calibration", True, T0)
    assert extract(item, FULL_RESULTS, config=V0_CONFIG, pack=PACK, taxonomy=TAX) == {}

def test_observations_carry_config_and_provisional():
    out = extract(ExtractionItem("a", "read_aloud", True, T0), ProviderResults(pronunciation=VEST_AS_WEST),
                  config=V0_CONFIG, pack=PACK, taxonomy=TAX)
    assert set(out) == {Detector.AZURE_PA}
    vw = [o for o in out[Detector.AZURE_PA] if o.error_key == "sound.sub.v.w"]
    assert vw and all(o.scoring_config_id == "v0" and o.provisional and o.attempt_id == "a" for o in vw)

def test_phone_probe_is_drill_only_under_v0(): ...      # probe result present -> out[PHONE_PROBE] == ()
def test_calibrated_key_is_firm(): ...                  # CAL_CONFIG enabling v.w -> provisional False, id == CAL_CONFIG.id
def test_disabled_key_writes_nothing(): ...             # CAL_CONFIG disabling v.w -> no sound.sub.v.w observations
def test_unscripted_sound_evidence_weighs_half(): ...   # step "speak" -> azure observations weight 0.5
def test_coach_without_transcript_is_empty(): ...       # out[COACH] == ()
```

```python
# tests/domain/extraction/test_extract_properties.py
@given(item=extraction_items(), results=provider_results(), config=scoring_configs())
def test_misses_never_exceed_opportunities(item, results, config): ...
    # per (detector, key): misses <= observations; slow_start <= 1 per attempt; each fluency/grammar key
    # has exactly len(sentences) observations when enabled; structure/clarity <= 1 per attempt

@given(item=extraction_items(), results=provider_results(), config=scoring_configs())
def test_extraction_is_deterministic(item, results, config): ...
    # extract(...) == extract(deepcopy inputs); pack hypotheses given in shuffled order -> same output

@given(item=extraction_items(), results=provider_results(), config=scoring_configs())
def test_provisional_matches_config_exactly(item, results, config): ...
    # every o: rule = config.rule_for(o.detector, TAX.get(o.error_key)); rule is not None
    #          and o.provisional == rule.provisional and o.scoring_config_id == config.id
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `uv run pytest tests/domain/extraction -q`
Expected: FAIL (`ModuleNotFoundError: nosolear.domain.extraction.fluency`).

- [ ] **Step 3: Implement `fluency.py`, `coach.py` and `extract.py`** to the rules above.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/domain -q && uv run pyright`
Expected: all pass.

- [ ] **Step 5: Commit, open the PR, merge when green**

```bash
git fetch origin && git switch -c p0e/04-extraction origin/main
git add apps/api docs/superpowers/HANDOFF.md
git commit -m "Extract fluency and coach observations and combine detectors in one pure extract"
git push -u origin p0e/04-extraction && gh pr create --fill
gh pr checks --watch && gh pr merge --squash
```

---

### Task 5: The extract job step, the re-scoring job and `nosolear rescore`

**Files:**
- Create:
  - `apps/api/src/nosolear/app/extract_attempt.py`, `app/rescore.py`, `app/scoring_steps.py`
  - `apps/api/src/nosolear/api/rescore_routes.py`
  - `apps/api/src/nosolear/first_run_cli.py`
  - `apps/api/tests/oracle_voice.py`, `apps/api/tests/harness.py`
- Modify:
  - `persistence/scoring_repository.py`: add `ExtractionInputsRepository`.
  - `ports/scoring_stores.py`: add `ExtractionInputs`.
  - `ports/stores.py` and `persistence/repositories.py`: `ProfileWriter.replace`.
  - `app/rebuild_profile.py`: `session_id` and `reason` parameters.
  - `api/deps.py`: register the `extract` step and the `rescore` kind; amend 0d's step predicates.
  - `api/app.py`: router.
  - `cli.py`: dispatch to `first_run_cli`.
  - `apps/web/src/shared/api/*` (regenerated).
- Test: `tests/app/test_extract_attempt.py`, `tests/app/test_rescore.py`, `tests/api/test_rescore_api.py`, `tests/test_cli_rescore.py`

**Interfaces:**
- **Consumes:**
  - Task 4's `extract`, `ExtractionItem` and `ProviderResults`.
  - Task 2's repositories.
  - 0d: `RawAnalysis`, `decode` and `encode`, and the step classes for score, transcribe, probe and coach.
  - 0c: the step registry, `JobQueue.enqueue`, `JobAcceptedOut`, `ApiClient` and the `main(argv, *, client=None)` hook.
- **Produces:**
  - **`ExtractionInputs` (port) / `ExtractionInputsRepository(engine)`:**
    - `item(attempt_id: str) -> ExtractionItem | None`. `observed_at` is the recording's `created_at`, else the attempt's.
    - `analyses(attempt_id: str) -> list[RawAnalysis]`.
    - `rescorable_attempt_ids() -> list[str]`: attempts that are not `calibration` and have at least one analysis, ordered by `(created_at, id)`.
  - **`app/extract_attempt.py`:**
    - `collect_results(analyses: Iterable[RawAnalysis]) -> tuple[ProviderResults, tuple[str, ...]]`: the second element lists the kinds whose `decode` raised `ValueError`. Those are skipped, and nothing about them is logged except the kind.
    - `ExtractSummary(attempt_id: str, scoring_config_id: str, written: int, undecodable: tuple[str, ...])`.
    - `extract_attempt(*, attempt_id: str, inputs: ExtractionInputs, configs: ScoringConfigReader, extractions: ExtractionWriter, pack: LanguagePack, taxonomy: Taxonomy, clock: Clock) -> ExtractSummary`: extracts under `configs.newest()` and writes each detector through `extractions.write`.
  - **`app/rescore.py`:**
    - `RescoreSummary(scoring_config_id: str, attempts: int, observations: int, undecodable: int)`.
    - `rescore(*, inputs, configs, extractions, observations: ObservationReader, profiles: ProfileWriter, pack, taxonomy, clock, on_progress: Callable[[float], None] = _ignore) -> RescoreSummary`. It loops over `rescorable_attempt_ids()`, then calls `rebuild_profile(..., reason="rebuild")`. Its parameters include no provider port.
  - **`app/scoring_steps.py`:**
    - `ExtractStep` (name `"extract"`, `needs=()`, always applies): `extract_attempt`, then `rebuild_profile(..., reason=None)`.
    - `RescoreStep` (name `"rescore"`): `rescore` with job progress.
  - **`rebuild_profile(*, observations, profiles, taxonomy, pack, clock, config=DEFAULT_CONFIG, session_id: str | None = None, reason: str | None = "rebuild") -> Profile`:** `reason=None` calls `profiles.replace(profile)`, which replaces the entries and takes no snapshot.
  - **Step predicates (amending 0d):**
    - transcribe and coach skip `step == "calibration"`.
    - probe applies only when the attempt is scripted and one of these holds: its step is `calibration` or `drill`, or `enabled_keys(newest config, PHONE_PROBE, tracked keys)` is non-empty.
  - **`POST /api/rescore`:** `operation_id="startRescore"`, 202 `JobAcceptedOut`. It enqueues `kind="rescore"` with no attempt.
  - **`first_run_cli.py`:**
    - `register(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None`.
    - `run(args: argparse.Namespace, client: ApiClient) -> int | None`.
    - Command `nosolear rescore` posts, follows the job, and prints `Re-scoring {status}: job {job_id}`.
  - **Test doubles:**
    - `tests/oracle_voice.py`:
      - `OracleVoice(user_errors: Mapping[str, str] = {}, calibration_set: CalibrationSet | None = None)`, with `.synthesizer`, `.scorer`, `.transcriber` and `.probe`, a `.calls: Counter[str]` (one counter per port), and `.fail_all(exc: Exception)`.
      - Each new text spoken through `.synthesizer` gets the next id `n` and a seeded-noise 16 kHz mono 16-bit WAV of `1000 + 10·n` ms, so the other ports can recover what was "said" from the clip's duration.
      - `.scorer` returns `encode(PronunciationResult)` for the reference text, built from a small grapheme-to-phone map (`th`, `sh`, `ch`, `ng` digraphs; vowels → `ə`). It substitutes where the spoken text is the calibration respelling of the reference word, or where `user_errors` maps a phone (e.g. `{"v": "w"}`).
      - `.probe` returns `encode(PhoneProbeResult)` from the same map, all `match` ops, plus a vowel `ins` at position 0 when the spoken text is an `is…` respelling.
      - `.transcriber` returns the spoken words at 400 ms each, starting at 600 ms.
    - `tests/harness.py`:
      - A `make_harness(*, probe: bool = False)` fixture factory, plus a default `harness` fixture.
      - It builds `create_app(Settings(data_dir=tmp_path), providers=ProviderPorts(...oracle..., probe=voice.probe if probe else None, coach=FakeCoach()))`.
      - A `Harness` exposes `client`, `voice`, `engine`, `drain()`, `upload(attempt_id, text) -> job_id` (synthesizes `text` with `voice.synthesizer` and posts it), `attempt(step=..., scripted=..., reference_text=..., session_kind="daily") -> attempt_id`, `observations() -> list[Observation]` and `ledger_rows() -> int`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/app/test_extract_attempt.py
def test_extract_step_stamps_v0_and_provisional(harness):
    a = harness.attempt(step="read_aloud", scripted=True, reference_text="Seven vans.")
    harness.voice.user_errors["v"] = "w"
    harness.upload(a, "Seven vans."); harness.drain()
    obs = [o for o in harness.observations() if o.error_key == "sound.sub.v.w"]
    assert obs and all(o.scoring_config_id == "v0" and o.provisional and o.outcome is MISS for o in obs)

def test_resumed_job_does_not_double_count(db_engine): ...
    # extract_attempt twice on the same stored analyses -> second summary.written == 0, row count unchanged

def test_calibration_attempts_write_no_observations(harness): ...   # step "calibration" -> 0 observations, 0 extractions
def test_probe_skipped_under_v0_and_run_for_calibration(make_harness): ...  # probe=True: probe calls: baseline 0, calibration 1
def test_transcriber_and_coach_skip_calibration(harness): ...
def test_undecodable_analysis_is_skipped_not_fatal(db_engine): ...  # corrupt raw_json -> summary.undecodable == ("pronunciation",)
def test_extract_rebuilds_profile_without_snapshot(harness): ...    # profile_entries filled; profile_snapshots count 0
```

```python
# tests/app/test_rescore.py
def test_rescore_makes_no_provider_calls_and_spends_no_quota(harness):
    a = scored_baseline_attempt(harness)                # uploaded and analyzed under v0
    calls, ledger = sum(harness.voice.calls.values()), harness.ledger_rows()
    harness.voice.fail_all(AssertionError("provider called during re-score"))
    add_config(harness, CAL_CONFIG)                     # enables azure_pa for sound.sub.v.w
    summary = rescore(**rescore_deps(harness))
    assert summary.attempts == 1 and summary.scoring_config_id == CAL_CONFIG.id
    assert sum(harness.voice.calls.values()) == calls and harness.ledger_rows() == ledger
    current = ObservationRepository(harness.engine).current()
    assert {o.scoring_config_id for o in current if o.attempt_id == a} == {CAL_CONFIG.id}
    assert any(o.scoring_config_id == "v0" for o in ObservationRepository(harness.engine).all())  # appended, not replaced

def test_rescore_is_idempotent(harness): ...            # second run: observations == 0
def test_rescore_skips_calibration_attempts(harness): ...
def test_profile_uses_newest_config_per_attempt(harness): ...   # v.w entry provisional before, firm after
def test_rescore_signature_has_no_provider_port():
    assert not {"scorer", "transcriber", "probe", "synthesizer", "coach"} & set(inspect.signature(rescore).parameters)
```

```python
# tests/api/test_rescore_api.py
def test_rescore_endpoint_queues_a_rescore_job(harness):
    r = harness.client.post("/api/rescore")
    assert r.status_code == 202
    harness.drain()
    assert harness.client.get(f"/api/jobs/{r.json()['job_id']}").json()["status"] == "done"
def test_openapi_operation_id(): assert create_app().openapi()["paths"]["/api/rescore"]["post"]["operationId"] == "startRescore"
```

```python
# tests/test_cli_rescore.py
def test_cli_rescore_follows_job(harness, capsys):
    assert main(["rescore"], client=ApiClient(http=harness.client)) == 0
    assert "Re-scoring done: job " in capsys.readouterr().out
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `uv run pytest tests/app tests/api/test_rescore_api.py tests/test_cli_rescore.py -q`
Expected: FAIL (no `extract_attempt`, no `/api/rescore`).

- [ ] **Step 3: Implement the use cases, steps, route, CLI and test doubles** to the Interfaces block. In `api/deps.py`:
- Append `ExtractStep` to the analyze kind's steps.
- Register `rescore` with `[RescoreStep]`.
- Pass `configs` into 0d's probe step for its new predicate.

`first_run_cli.register` is called from `cli._parser()`. `cli.main` returns `first_run_cli.run(args, client)` whenever that is not `None`.

- [ ] **Step 4: Run the tests, regenerate the API types, and confirm they pass**

Run: `uv run pytest -q && uv run pyright && cd ../.. && make gen-api && make lint && git status --short apps/web`
Expected: all pass; `apps/web/src/shared/api/openapi.json` and `schema.d.ts` change (they gain `/api/rescore`), and nothing else under `apps/web` does.

- [ ] **Step 5: Commit, open the PR, merge when green**

```bash
git fetch origin && git switch -c p0e/05-extract-step-rescore origin/main
git add apps/api apps/web/src/shared/api docs/superpowers/HANDOFF.md
git commit -m "Extract observations in analyze jobs and re-score history without provider calls"
git push -u origin p0e/05-extract-step-rescore && gh pr create --fill
gh pr checks --watch && gh pr merge --squash
```

---

### Task 6: Seed content: the calibration set and the baseline protocol

**Files:**
- Create:
  - `content/baseline/protocol.json`
  - `apps/api/src/nosolear/domain/content.py`
  - `apps/api/src/nosolear/adapters/content_files.py`
  - `apps/api/src/nosolear/persistence/content_repository.py`
  - `apps/api/src/nosolear/ports/content_store.py`
- Modify:
  - `content/calibration/items.json`: convert 0b's port into the shape below and extend it.
  - `content/packs/nepali/`: only if 0b stored calibration extras elsewhere; move them into `calibration.json`.
  - `api/app.py`: load and sync the content in the lifespan; `create_app(..., content: SeedContent | None = None)`. Passing `content` skips loading the files, for tests.
  - `api/deps.py`: `get_seed_content`.
  - `tests/harness.py`: `make_harness(*, content: SeedContent | None = None, ...)`.
  - `persistence/models.py`: kind CHECK from `ContentKind`.
- Test: `tests/domain/test_content.py`, `tests/adapters/test_content_files.py`, `tests/persistence/test_content_repository.py`

**Interfaces:**
- **Consumes:** 0b's content root (`CONTENT_DIR`) and the active pack (`calibration_emphasis`); `Taxonomy`; `AttemptStep`.
- **Produces, in `domain/content.py`:**
  - `class ContentKind(StrEnum)`: `PROMPT`, `PASSAGE_SENTENCE`, `MINIMAL_PAIR`, `DRILL_SENTENCE`, `STARTER`, `QUICK_QUESTION`, `CALIBRATION_WORD`, with the §7 values.
  - `ContentItem(id: str, kind: ContentKind, text: str, target_keys: tuple[str, ...], source: Literal["seed", "coach"] = "seed")`.
  - `CalibrationWord(item_id: str, error_key: str, word: str, respelling: str, description: str)`; `item_id = f"cal:{error_key}:{word}"`.
  - `CalibrationSet(takes_per_word: int, words: tuple[CalibrationWord, ...])`, with `keys() -> tuple[str, ...]` (file order), `words_for(key) -> tuple[CalibrationWord, ...]` and `word(item_id) -> CalibrationWord | None`.
  - `BaselineItem(item: ContentItem, stand_in: str | None, tokens: Mapping[str, tuple[str, ...]])`.
  - `BaselineSection(name: str, step: AttemptStep, items: tuple[BaselineItem, ...], max_seconds: int | None, start_limit_seconds: int | None)`.
  - `BaselineProtocol(version: int, sections: tuple[BaselineSection, ...], stress_pairs: tuple[str, ...])`.
  - `SeedContent(calibration_set: CalibrationSet, protocol: BaselineProtocol)`.
  - `class ContentInvalid(ValueError)`.
  - `validate_calibration_set(cs: CalibrationSet, taxonomy: Taxonomy, *, min_words: int = 5) -> None`.
  - `validate_baseline_protocol(p: BaselineProtocol, taxonomy: Taxonomy) -> None`.
  - `seed_items(content: SeedContent) -> tuple[ContentItem, ...]`.
  - `calibration_instruction(w: CalibrationWord, *, deliberate: bool, take: int, takes: int) -> str`.
  - `stand_in_text(w: CalibrationWord, *, deliberate: bool) -> str`: the respelling for a deliberate take, else the word.
  - `BASELINE_PROTOCOL_VERSION = 1`.
- **Produces, elsewhere:**
  - `adapters/content_files.py`:
    - `load_calibration_set(content_dir: Path, pack_id: str) -> CalibrationSet` reads `calibration/items.json` and merges `packs/<pack_id>/calibration.json` when present (same shape; extra words appended to their key).
    - `load_baseline_protocol(content_dir: Path) -> BaselineProtocol`.
    - `load_seed_content(content_dir: Path, pack_id: str) -> SeedContent` loads both and validates them.
    - Malformed JSON or missing fields raise `ContentInvalid`. Paths are fixed relative to `content_dir`; `pack_id` is already validated as `^[a-z0-9_]+$` by settings.
  - `ContentRepository(engine)`:
    - `sync_seed(items: Sequence[ContentItem], *, now: datetime) -> SyncSummary(added: int, retired: int)` inserts missing ids and retires seed ids that are gone. An existing id whose kind, text or keys changed raises `ContentConflict(ValueError)`, because content ids are immutable so past attempts keep their meaning.
    - `get(item_id) -> ContentItem | None`.
  - The lifespan calls `sync_seed` after migrations.

**`content/calibration/items.json`:**

```json
{"version": 1, "takes_per_word": 2,
 "keys": [{"error_key": "sound.sub.v.w", "description": "W instead of V",
           "words": [{"word": "vest", "respelling": "west"}, ...]}, ...]}
```

Keep all 26 salvaged words with their respellings and descriptions (from `p0b/spikes:spikes/items.py`, as ported by 0b). Then add these, so that every key has exactly 5 words, which means 10 error takes and 5 TTS controls:

| Key | Added (word → respelling) |
|---|---|
| `sound.sub.v.w` | vine → wine, veil → wail |
| `sound.sub.w.v` | wet → vet, wail → veil, worse → verse |
| `sound.sub.f.p` | fast → past, feel → peel |
| `sound.sub.θ.t` | thin → tin, thought → taught |
| `sound.sub.ð.d` | then → den, those → doze, there → dare |
| `sound.sub.ʃ.s` | shell → sell, shine → sign |
| `sound.sub.s.ʃ` | sell → shell, sign → shine, seat → sheet |
| `sound.sub.z.dʒ` | zest → jest, zone → jone, zeal → jeal |
| `sound.sub.z.s` | prize → price, eyes → ice, rise → rice |
| `sound.ins.epenthesis_sC` | smile → ismile |

**Calibration copy** (salvaged; the insertion key uses the second form):
- Correct take: `Say "{word}" as correctly as possible, in General American.`
- Error take: `Say "{word}" with {description} — sounds like "{respelling}" (take {n} of {takes})`
- Insertion error take: `Say "{word}" with {description} — "{respelling}" (take {n} of {takes})`

**`content/baseline/protocol.json`:** written for this project, not copied from anywhere. Sections in this order:
1. **`read_aloud`** (step `read_aloud`): passage A, about 150 words, one `passage_sentence` item per sentence. Each sentence has `tokens: {error_key: [words]}` annotating where each tracked contrast occurs. Passage-level `stress_pairs` lists words that appear in both stress forms (at least `record`).
2. **`word_list`** (step `word_list`): four `minimal_pair` items of five words each, in this order: `vest west vine wine fan`, `pan sip ship sea she`, `think thin this then zest`, `jest zoo school speak street`.
3. **`free_talk`** (step `speak`, `max_seconds` 90): one `prompt`, "Describe a place you love to visit and why." (salvaged).
4. **`rapid_questions`** (step `quick_answer`, `max_seconds` 15, `start_limit_seconds` 5): five `quick_question` items, each at most 12 words and answerable by anyone without personal details.
5. **`articulate`** (step `articulate`, `max_seconds` 60): one point-reason-example `prompt`.

Every unscripted item has a `stand_in` answer text (two to four sentences) for TTS runs. Ids follow the pattern `ba-ra-01`, `ba-wl-01`, `ba-ft-01`, `ba-rq-01`, `ba-ar-01`.

**Validation rules.**
- **Calibration set:**
  - Every key is in the taxonomy, is a SUB, INS or DEL key, and allows `azure_pa` or `phone_probe`.
  - Each key has at least `min_words` words, and `len(words) × takes_per_word ≥ 5`.
  - Ids are unique, and words and respellings are non-empty and differ.
- **Baseline protocol:**
  - Section names and steps are exactly the five above, in order, and ids are unique.
  - Passage A has 130–170 words and every sentence at most 25 words.
  - Every annotated token word appears in its sentence.
  - Every SUB and LOW key that `taxonomy.defined()` lists, and `sound.ins.epenthesis_sC`, has at least 3 annotated tokens across the passage.
  - Each stress-pair word occurs at least twice in the passage.
  - The word list has exactly 20 words, and there are exactly 5 rapid questions with `start_limit_seconds == 5`.
  - Every unscripted item has a `stand_in`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/adapters/test_content_files.py  (reads the committed content/)
@pytest.mark.parametrize("pack_id", sorted(p.name for p in (CONTENT_DIR / "packs").iterdir()))
def test_every_pack_calibration_set_meets_the_minimum(pack_id):
    cs = load_calibration_set(CONTENT_DIR, pack_id)
    validate_calibration_set(cs, TAX)
    for key in cs.keys():
        assert len(cs.words_for(key)) >= 5 and len(cs.words_for(key)) * cs.takes_per_word >= 5

def test_salvaged_words_are_kept():
    words = {w.word for w in load_calibration_set(CONTENT_DIR, "neutral").words}
    assert SALVAGED_26 <= words                  # vest very van west wine fan fine coffee think three thanks
                                                 # this they ship she shop sip see zoo zero zip buzz school speak street sport
def test_nepali_emphasis_keys_are_calibratable():
    cs = load_calibration_set(CONTENT_DIR, "nepali")
    for key in load_pack(CONTENT_DIR, "nepali").calibration_emphasis:
        if TAX.get(key).family in (Family.SUB, Family.INS, Family.DEL):
            assert key in cs.keys()

def test_committed_baseline_protocol_is_valid():
    validate_baseline_protocol(load_baseline_protocol(CONTENT_DIR), TAX)
```

```python
# tests/domain/test_content.py  (synthetic content built in the test)
def test_rejects_a_key_with_too_few_words(): ...              # 4 words -> ContentInvalid
def test_rejects_a_non_sound_calibration_key(): ...           # "grammar.article" -> ContentInvalid
def test_rejects_a_token_missing_from_its_sentence(): ...
def test_rejects_thin_coverage_of_a_contrast(): ...           # sound.sub.v.w with 2 tokens -> ContentInvalid
def test_rejects_sections_out_of_order(): ...
def test_instruction_copy():
    w = CalibrationWord("cal:sound.sub.v.w:vest", "sound.sub.v.w", "vest", "west", "W instead of V")
    assert calibration_instruction(w, deliberate=True, take=1, takes=2) == 'Say "vest" with W instead of V — sounds like "west" (take 1 of 2)'
    assert calibration_instruction(w, deliberate=False, take=1, takes=2) == 'Say "vest" as correctly as possible, in General American.'
    assert stand_in_text(w, deliberate=True) == "west"
```

```python
# tests/persistence/test_content_repository.py
def test_sync_inserts_then_retires(db_engine): ...            # second sync without one item -> retired == 1, get() still returns it
def test_sync_refuses_a_changed_text_for_an_existing_id(db_engine): ...   # ContentConflict
def test_app_startup_syncs_committed_content(client_with_tmp_db): ...     # content_items has every seed id
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `uv run pytest tests/domain/test_content.py tests/adapters tests/persistence/test_content_repository.py -q`
Expected: FAIL (`ModuleNotFoundError: nosolear.domain.content`).

- [ ] **Step 3: Write the content files, then implement the domain types, validators, loader and repository**

Follow the Interfaces block and the rules above. Passage A must also read naturally aloud. The validator checks annotated contrasts; the reviewer reads the passage for every other General American phoneme.

- [ ] **Step 4: Run the tests and the hygiene check, and confirm they pass**

Run: `uv run pytest -q && uv run pyright && cd ../.. && git ls-files content | bash scripts/check-no-personal-data.sh`
Expected: all pass; hygiene exits 0.

- [ ] **Step 5: Commit, open the PR, merge when green**

```bash
git fetch origin && git switch -c p0e/06-seed-content origin/main
git add content apps/api docs/superpowers/HANDOFF.md
git commit -m "Add the calibration set and baseline protocol as validated seed content"
git push -u origin p0e/06-seed-content && gh pr create --fill
gh pr checks --watch && gh pr merge --squash
```

---

### Task 7: The calibration rule and calibrated configs

**Files:**
- Create: `apps/api/src/nosolear/domain/calibration.py`
- Test: `tests/domain/test_calibration.py`, `tests/domain/test_calibration_properties.py`

**Interfaces:**
- **Consumes:** Task 1's `ScoringConfig`, `KeyRule`, `TrialCounts`, `V0_CONFIG` and `CALIBRATED_THRESHOLDS`; Task 3's `azure_opportunities` and `probe_opportunities`; Task 6's `CalibrationSet`; 0d's `PronunciationResult` and `PhoneProbeResult`.
- **Produces, in `domain/calibration.py`:**
  - **Trials:**
    - `class TrialKind(StrEnum)`: `ERROR = "error"`, `CONTROL = "control"`.
    - `Trial(error_key: str, detector: Detector, kind: TrialKind, attempt_id: str | None, tts_hash: str | None, flagged: bool | None)`. `__post_init__` requires exactly one of `attempt_id` and `tts_hash`, and an `attempt_id` for an `ERROR`.
    - `tally(trials: Iterable[Trial]) -> dict[tuple[Detector, str], TrialCounts]`. Trials with `flagged is None` are skipped. The rest count as follows:
      - error trials add to `errors`, and `hits` when flagged;
      - control trials with a `tts_hash` add to `controls`, and `false_alarms` when flagged;
      - control trials with an `attempt_id` add to `correct_takes`, and `correct_flags` when flagged.
  - **The rule:**
    - `CalibrationRule(min_errors: int = 5, min_controls: int = 5, min_hit_rate: Fraction = Fraction(4, 5), max_false_alarm_rate: Fraction = Fraction(1, 5))` and `DEFAULT_RULE`.
    - `covers(c: TrialCounts, rule: CalibrationRule = DEFAULT_RULE) -> bool`: `errors ≥ min_errors and controls ≥ min_controls`.
    - `passes(c: TrialCounts, rule: CalibrationRule = DEFAULT_RULE) -> bool`: `covers(c)`, `Fraction(hits, errors) ≥ min_hit_rate` and `Fraction(false_alarms, controls) ≤ max_false_alarm_rate`.
  - **Results:**
    - `PairResult(detector: Detector, error_key: str, counts: TrialCounts, covered: bool, enabled: bool, warning: str | None)`, with the properties `hit_rate`, `false_alarm_rate` and `correct_take_flag_rate` (each `float | None`).
    - `evaluate(trials: Iterable[Trial], rule: CalibrationRule = DEFAULT_RULE) -> tuple[PairResult, ...]`, sorted by `(error_key, detector)` and independent of input order.
    - `build_calibrated_config(*, config_id: str, run_id: str, results: Sequence[PairResult], base: ScoringConfig = V0_CONFIG) -> ScoringConfig`. The config has kind `CALIBRATED` and `base`'s family rules and thresholds, plus one `KeyRule(detector, key, enabled=result.enabled, thresholds=CALIBRATED_THRESHOLDS, counts)` for each covered result.
  - **Flagging a single clip:** `flagged(detector: Detector, error_key: str, result: PronunciationResult | PhoneProbeResult, *, thresholds: Thresholds = CALIBRATED_THRESHOLDS) -> bool | None`. It is `None` when the clip gives that key no opportunity; otherwise it is whether any opportunity was missed.
  - **Planning:**
    - `calibratable_detectors(*, azure_nbest: bool, phone_probe_ready: bool) -> frozenset[Detector]`.
    - `PlannedToken(order: int, item_id: str, error_key: str, word: str, deliberate: bool, take: int)`.
    - `CalibrationPlan(detectors: Mapping[str, tuple[Detector, ...]], tokens: tuple[PlannedToken, ...])`.
    - `plan_calibration(cs: CalibrationSet, *, emphasis: Sequence[str], available: frozenset[Detector], taxonomy: Taxonomy) -> CalibrationPlan`:
      - Key order: the pack's `emphasis` keys that are in the set, in emphasis order, then the remaining set keys in file order.
      - A key's detectors are the sorted intersection of its allowed detectors with `available`. Keys with none are dropped.
      - Per word: the correct take first (`take=1`), then error takes `1..takes_per_word`.
      - `order` counts from 1.

**Warning copy** (set only when `enabled` and `5·correct_flags > correct_takes`; percentages are whole numbers, rounded):
`Your own correct takes were flagged {p}% of the time (TTS controls: {q}%). This detector may count errors you didn't make on this key.`

- [ ] **Step 1: Write the failing tests**

```python
# tests/domain/test_calibration.py
def test_rule_boundaries():
    assert passes(TrialCounts(errors=10, hits=8, controls=5, false_alarms=1, correct_takes=0, correct_flags=0))
    assert not passes(TrialCounts(10, 7, 5, 1, 0, 0))     # 70% hits
    assert not passes(TrialCounts(10, 8, 5, 2, 0, 0))     # 40% false alarms
    assert not passes(TrialCounts(4, 4, 5, 0, 0, 0))      # too few error tokens
    assert not passes(TrialCounts(10, 10, 4, 0, 0, 0))    # too few controls

def test_flagged_azure_substitution():
    assert flagged(Detector.AZURE_PA, "sound.sub.v.w", pa_result([vest_said_as_west()])) is True
    assert flagged(Detector.AZURE_PA, "sound.sub.v.w", pa_result([vest_said_correctly()])) is False
    assert flagged(Detector.AZURE_PA, "sound.sub.v.w", pa_result([pa_word("fan", ...)])) is None   # no /v/

def test_no_nbest_means_no_trial_counted():
    assert flagged(Detector.AZURE_PA, "sound.sub.v.w", pa_result([vest_said_as_west()], has_nbest=False)) is None

def test_flagged_probe_epenthesis(): ...
def test_correct_take_flags_warn_but_do_not_disable():
    (r,) = evaluate(trials(errors=10, hits=10, controls=5, false_alarms=0, correct_takes=5, correct_flags=3))
    assert r.enabled and r.warning == ("Your own correct takes were flagged 60% of the time (TTS controls: 0%). "
                                       "This detector may count errors you didn't make on this key.")

def test_calibrated_config_covers_only_covered_pairs():
    cfg = build_calibrated_config(config_id="c1", run_id="r1", results=[ENABLED_VW, FAILED_FP, UNCOVERED_TT])
    assert {(k.error_key, k.enabled) for k in cfg.key_rules} == {("sound.sub.v.w", True), ("sound.sub.f.p", False)}
    assert cfg.rule_for(Detector.AZURE_PA, TAX.get("sound.sub.θ.t")) == V0_CONFIG.rule_for(Detector.AZURE_PA, TAX.get("sound.sub.θ.t"))

def test_plan_orders_by_pack_emphasis_and_drops_keys_without_detectors():
    # SET_WITH_EPENTHESIS: sound.sub.v.w, sound.sub.f.p, sound.ins.epenthesis_sC, 5 words each, in that file order
    plan = plan_calibration(SET_WITH_EPENTHESIS, emphasis=["sound.sub.f.p"], available=frozenset({Detector.AZURE_PA}), taxonomy=TAX)
    assert list(plan.detectors) == ["sound.sub.f.p", "sound.sub.v.w"]        # epenthesis dropped: probe unavailable
    assert [(t.word, t.deliberate, t.take) for t in plan.tokens[:3]] == [("fan", False, 1), ("fan", True, 1), ("fan", True, 2)]

def test_plan_is_empty_with_no_detectors(): ...
def test_calibratable_detectors(): ...   # (False, False) -> {}; (True, False) -> {AZURE_PA}; (False, True) -> {PHONE_PROBE}
```

```python
# tests/domain/test_calibration_properties.py   (counts(): errors, controls 0..20, hits <= errors, fa <= controls, ...)
@given(c=counts())
def test_enabled_iff_rule(c): assert passes(c) == (c.errors >= 5 and c.controls >= 5 and 5 * c.hits >= 4 * c.errors and 5 * c.false_alarms <= c.controls)
@given(c=counts())
def test_adding_a_hit_never_disables(c): assert not passes(c) or passes(replace(c, errors=c.errors + 1, hits=c.hits + 1))
@given(c=counts())
def test_adding_a_false_alarm_or_a_miss_never_enables(c): ...
@given(c=counts())
def test_adding_a_clean_control_never_disables(c): ...
@given(c=counts(), takes=st.integers(0, 20), flags=st.integers(0, 20))
def test_correct_takes_never_change_enablement(c, takes, flags): ...
@given(c=counts(max_errors=4) | counts(max_controls=4))
def test_too_few_trials_never_enable(c): assert not passes(c)
@given(ts=trial_lists(), seed=st.randoms())
def test_evaluate_is_order_independent(ts, seed): ...
@given(ts=trial_lists())
def test_calibrated_config_enables_exactly_passing_covered_pairs(ts): ...
    # for every result: covered -> (rule_for(...) is not None) == passes(counts); uncovered -> equals V0_CONFIG's rule
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `uv run pytest tests/domain/test_calibration.py tests/domain/test_calibration_properties.py -q`
Expected: FAIL (`ModuleNotFoundError: nosolear.domain.calibration`).

- [ ] **Step 3: Implement `domain/calibration.py`**

Follow the Interfaces block. `flagged` runs the Task 3 opportunity function on `keys=frozenset({error_key})` with `thresholds_for=lambda _: thresholds`, then filters to that key.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/domain -q && uv run pyright`
Expected: all pass, with no falsifying examples.

- [ ] **Step 5: Commit, open the PR, merge when green**

```bash
git fetch origin && git switch -c p0e/07-calibration-rule origin/main
git add apps/api docs/superpowers/HANDOFF.md
git commit -m "Add the calibration rule, plan and calibrated scoring config"
git push -u origin p0e/07-calibration-rule && gh pr create --fill
gh pr checks --watch && gh pr merge --squash
```

---

### Task 8: The calibration session: API, job and CLI

**Files:**
- Create:
  - `apps/api/src/nosolear/persistence/calibration_repository.py`
  - `apps/api/src/nosolear/ports/calibration_store.py`
  - `apps/api/src/nosolear/app/calibrate.py`, `app/calibrate_job.py`
  - `apps/api/src/nosolear/api/calibration_routes.py`, `api/calibration_schemas.py`
- Modify:
  - `api/deps.py`: register the `calibrate` kind and provide `get_calibration_store` and `get_available_detectors`.
  - `api/app.py`: router.
  - `first_run_cli.py`: `calibrate start|status|skip|finish`.
  - `tests/harness.py`: every harness seeds an `azure_pa` `provider_capabilities` row with n-best and prosody, so `azure_pa` is calibratable.
  - `docs/ARCHITECTURE.md`: §9.2 and §18, recording that prosody is not calibrated in 0e.
  - `apps/web/src/shared/api/*` (regenerated).
- Test: `tests/persistence/test_calibration_repository.py`, `tests/app/test_calibrate.py`, `tests/api/test_calibration_api.py`, `tests/test_cli_calibrate.py`

**Interfaces:**
- **Consumes:**
  - Task 7: `plan_calibration`, `evaluate`, `build_calibrated_config`, `flagged`, `Trial` and `calibratable_detectors`.
  - Task 6: `SeedContent` and `calibration_instruction`.
  - Task 5: `ExtractionInputs.analyses` and the `rescore` kind.
  - Task 2: `ScoringConfigWriter`.
  - 0d: metered `Synthesizer.synthesize`, `PronunciationScorer.score` and `PhoneProbe.probe`, plus the capability store and the phone-probe readiness row.
  - 0c: `JobQueue` and the jobs and recordings tables.
- **Produces:**
  - **`CalibrationStore` (port) / `CalibrationRepository(engine)`:**
    - `running()` and `latest()`, each returning `CalibrationRunRecord | None`.
    - `start(*, run_id, session_id, plan: CalibrationPlan, now) -> CalibrationRunRecord`. In one `BEGIN IMMEDIATE` transaction it:
      - raises `RunAlreadyOpen` if a run is running;
      - creates a `calibration` session;
      - creates one attempt per token (`step="calibration"`, `scripted=True`, `reference_text=word`, `content_item_id=item_id`, `created_at = now + order µs` so that `created_at` order is plan order);
      - creates the run (`running`);
      - creates one trial row per (token, detector of its key): `ERROR` for deliberate tokens, `CONTROL` with the attempt for correct takes.
    - `skip(*, run_id, now) -> CalibrationRunRecord`: marks the running run `skipped`, or else inserts a new `skipped` run with no session.
    - `items(run_id) -> list[CalibrationItemRecord]`.
    - `trials(run_id) -> list[TrialRecord]`.
    - `control_analysis(tts_hash, run_id, kind) -> RawAnalysis | None` and `add_control_analysis(tts_hash, run_id, analysis)`.
    - `add_control_trials(run_id, tts_hash, pairs: Sequence[tuple[str, Detector]])`, idempotent.
    - `set_flags(flags: Mapping[int, bool | None])`.
    - `complete(*, run_id, config, capabilities, now)`: in one transaction, inserts the config and marks the run `done` with its `scoring_config_id`.
    - `open_calibrate_job() -> str | None`.
  - **Records:**
    - `CalibrationRunRecord(id, session_id: str | None, status: Literal["running", "done", "skipped"], scoring_config_id: str | None, started_at, completed_at)`.
    - `CalibrationItemRecord(attempt_id, order, item_id, error_key, word, deliberate, recorded: bool, job_status: str | None)`.
    - `TrialRecord(id: int, trial: Trial)`.
  - **`app/calibrate.py`:**
    - Errors: `NothingToCalibrate`, `CalibrationNotRunning`, `NothingRecorded` and `TokensPending` (all `ValueError`).
    - `CalibrationView(run: CalibrationRunRecord, items: tuple[CalibrationItemView, ...], results: tuple[PairResult, ...])`.
    - `CalibrationItemView(attempt_id, order, error_key, word, deliberate, take, instruction, stand_in_text, recorded, job_status)`.
    - `start_calibration(*, store, content: SeedContent, pack, available: frozenset[Detector], taxonomy, clock) -> CalibrationView`: returns the running run if there is one; raises `NothingToCalibrate` on an empty plan.
    - `skip_calibration(*, store, clock) -> CalibrationView`.
    - `finish_calibration(*, store, queue) -> str`:
      - returns the open calibrate job's id if one exists;
      - raises `CalibrationNotRunning` when no run is running;
      - raises `NothingRecorded` when no token has a recording, so controls never spend quota for nothing;
      - raises `TokensPending` while any recorded token's analyze job is `queued` or `running`. Unrecorded tokens don't block; their trials stay `None`.
      - Otherwise it enqueues `kind="calibrate"`.
    - `calibration_view(*, store, content) -> CalibrationView | None`. `results` are computed from the stored trials with `evaluate` once the run is `done`.
  - **`app/calibrate_job.py`** (steps in order):
    - `ControlsStep` (`"controls"`). For each distinct word of the running run:
      - `clip = synthesizer.synthesize(word)`;
      - for each detector the word's keys use, if no control analysis is stored for `(clip.hash, run, kind)`, call the port (`score(clip.path, reference_text=word)` or `probe(...)`) and store the result;
      - `add_control_trials`;
      - then progress `i/n`.
      Any port error propagates, so the runner fails the step with its typed error and the run stays `running`.
    - `EvaluateStep` (`"evaluate"`, `needs=("controls",)`). If the run is already `done`, it does nothing. Otherwise:
      - decode each trial's analysis (the attempt's analysis of the detector's kind, or the control's);
      - `set_flags` from `flagged(...)` (`None` when the analysis is missing or undecodable);
      - `evaluate`, then `build_calibrated_config(config_id=uuid4().hex, run_id=...)`;
      - `complete(capabilities=...)`, with `{"azure_pa": {"nbest": ..., "prosody": ..., "provider_version": ...}, "phone_probe": {"ready": ...}}`.
    - `QueueRescoreStep` (`"queue_rescore"`, `needs=("evaluate",)`): `queue.enqueue("rescore")`.
  - **Routes** (`api/calibration_routes.py`; domain errors map to 409 with the safe messages below):
    - `POST /api/calibration` → 200 `CalibrationRunOut` (`startCalibration`).
    - `GET /api/calibration` → 200 `CalibrationRunOut`, or 404 when no run exists (`getCalibration`).
    - `POST /api/calibration/skip` → 200 `CalibrationRunOut` (`skipCalibration`).
    - `POST /api/calibration/finish` → 202 `JobAcceptedOut` (`finishCalibration`).
  - **Schemas:**
    - `CalibrationRunOut`: `run_id`, `session_id`, `status`, `scoring_config_id`, `started_at`, `completed_at`, `items: list[CalibrationItemOut]`, `results: list[CalibrationResultOut]`.
    - `CalibrationItemOut`: the fields of `CalibrationItemView`.
    - `CalibrationResultOut`: `detector`, `error_key`, the six counts, `covered`, `enabled`, `hit_rate`, `false_alarm_rate`, `correct_take_flag_rate`, `warning`.
  - **CLI:**
    - `nosolear calibrate start` prints `{order:>3}  {attempt_id}  {instruction}` per item.
    - `status` prints the recorded count over the total, and the results table when done.
    - `skip` prints `Calibration skipped. Scores stay provisional until you calibrate.`
    - `finish` follows the calibrate job and prints the enabled pairs.

**Safe 409 messages:**
- `NothingToCalibrate`: `No detector can be calibrated on this install: run nosolear doctor --probe, or skip calibration.`
- `TokensPending`: `Some calibration recordings are still being analyzed. Try again when their jobs finish.`
- `CalibrationNotRunning`: `No calibration run is in progress.`
- `NothingRecorded`: `Record at least one calibration word before finishing.`

- [ ] **Step 1: Write the failing tests**

```python
# tests/app/test_calibrate.py   (harness = make_harness(content=SeedContent(SMALL_SET, PROTOCOL)):
#                                SMALL_SET has v.w and f.p, 5 words each, takes_per_word=2)
def test_start_creates_session_attempts_and_trials(harness):
    view = start(harness)                                          # azure_pa available, probe not installed
    assert len(view.items) == 2 * 5 * 3
    assert count(harness.engine, "calibration_trials") == 30       # 20 error + 10 correct-take, one detector
    assert {i.instruction for i in view.items if i.word == "vest"} >= {'Say "vest" as correctly as possible, in General American.'}

def test_start_returns_the_open_run(harness): ...                  # second start -> same run id, no new attempts
def test_start_with_no_detectors_raises(harness): ...              # available={} -> NothingToCalibrate
def test_skip_without_a_run_records_a_skipped_run(harness): ...    # status "skipped", session_id None
def test_skip_marks_the_open_run_skipped(harness): ...
def test_finish_requires_settled_tokens(harness): ...              # one upload not drained -> TokensPending

def test_finish_runs_controls_evaluates_and_queues_rescore(harness):
    view = start(harness)
    for item in view.items:
        harness.upload(item.attempt_id, item.stand_in_text)        # oracle hears respellings as the deliberate error
    harness.drain()
    finish_calibration(store=store(harness), queue=queue(harness)); harness.drain()
    run = store(harness).latest()
    assert run.status == "done" and run.scoring_config_id is not None
    cfg = ScoringConfigRepository(harness.engine, TAX).newest()
    assert cfg.kind is ConfigKind.CALIBRATED and {(k.error_key, k.enabled) for k in cfg.key_rules} == {
        ("sound.sub.f.p", True), ("sound.sub.v.w", True)}
    assert jobs_of_kind(harness, "rescore") == ["done"]

def test_controls_are_synthesized_and_scored_once_per_run(harness):
    ...  # record voice.calls after the tokens are drained; finish, make evaluate fail once (monkeypatch), resume:
         # across both job runs the synthesizer and scorer were called exactly 10 times each (one per word)

def test_cap_exceeded_during_controls_keeps_run_running(harness):
    ...  # NOSOLEAR_CAP_AZURE_AUDIO_HOURS tiny -> job failed with CapExceeded, run "running",
         # no calibrated config, and no scorer call during the job (refused before the call)

def test_correct_take_flags_warn_but_do_not_disable(harness): ...  # oracle flags 3 of 5 correct "vest"-key takes
def test_finish_twice_returns_the_same_job(harness): ...
def test_a_done_run_can_be_started_again(harness): ...             # after done, start -> a new run id, new session
```

```python
# tests/api/test_calibration_api.py
def test_calibration_flow_over_http(harness):
    r = harness.client.post("/api/calibration"); assert r.status_code == 200 and r.json()["status"] == "running"
    assert harness.client.get("/api/calibration").json()["run_id"] == r.json()["run_id"]
    assert harness.client.post("/api/calibration/finish").status_code == 409   # NothingRecorded
    first = r.json()["items"][0]; harness.upload(first["attempt_id"], first["stand_in_text"]); harness.drain()
    assert harness.client.post("/api/calibration/finish").status_code == 202
def test_get_without_a_run_is_404(harness): ...
def test_nothing_to_calibrate_is_409_with_a_safe_message(harness): ...
def test_responses_never_contain_settings(harness): ...            # planted fake keys absent from every calibration response body
def test_openapi_operation_ids(): ...                               # the four ids above
```

```python
# tests/test_cli_calibrate.py
def test_cli_calibrate_start_lists_tokens(harness, capsys): ...    # 30 lines, each with an attempt id and an instruction
def test_cli_calibrate_skip(harness, capsys): ...
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `uv run pytest tests/app/test_calibrate.py tests/api/test_calibration_api.py tests/test_cli_calibrate.py tests/persistence/test_calibration_repository.py -q`
Expected: FAIL (`ModuleNotFoundError: nosolear.app.calibrate`).

- [ ] **Step 3: Implement the repository, use cases, job steps, routes, schemas and CLI**

Follow the Interfaces block. `get_available_detectors` in `api/deps.py` computes `calibratable_detectors(azure_nbest=<latest azure_pa capabilities' "nbest">, phone_probe_ready=<readiness phone_probe row is ready>)`. Every port the steps use comes from 0d's composition, cache → retry → metered → raw, so each control call reserves on the ledger. Update §9.2 and §18 of `docs/ARCHITECTURE.md` with the prosody decision.

- [ ] **Step 4: Run the tests, regenerate the API types, and confirm they pass**

Run: `uv run pytest -q && uv run pyright && cd ../.. && make gen-api && make lint`
Expected: all pass; only `apps/web/src/shared/api/*` changes under `apps/web`.

- [ ] **Step 5: Commit, open the PR, merge when green**

```bash
git fetch origin && git switch -c p0e/08-calibration-session origin/main
git add apps/api apps/web/src/shared/api docs/ARCHITECTURE.md docs/superpowers/HANDOFF.md
git commit -m "Add the calibration session with cached TTS controls and a calibrate job"
git push -u origin p0e/08-calibration-session && gh pr create --fill
gh pr checks --watch && gh pr merge --squash
```

---

### Task 9: Skill scores and the baseline report (domain)

**Files:**
- Create: `apps/api/src/nosolear/domain/skill_scores.py`, `apps/api/src/nosolear/domain/baseline_report.py`
- Test: `tests/domain/test_skill_scores.py`, `tests/domain/test_baseline_report.py`

**Interfaces:**
- **Consumes:** `Profile` and `ProfileEntry` (with `provisional`); `Observation`; 0d's `PronunciationResult`, `Transcript` and `CoachRubric`; Task 4's `FILLERS`, `normalize` and `sentences`.
- **Produces, in `domain/skill_scores.py`:**
  - `linear_score(value: float, *, zero_at: float, full_at: float) -> float`: 100 at `full_at`, 0 at `zero_at`, linear in between, clamped to [0, 100].
  - `SessionEvidence`, with these fields:
    - `scripted_pronunciation: tuple[PronunciationResult, ...]`
    - `sound_observations: tuple[Observation, ...]`
    - `quick_answers: tuple[Transcript, ...]`
    - `unscripted: tuple[Transcript, ...]`
    - `grammar_misses: int`
    - `articulate_rubric: CoachRubric | None`
  - `SkillScore(skill: Skill, score: float, values: Mapping[str, float], scores: Mapping[str, float])`.
  - `skill_scores(evidence: SessionEvidence) -> tuple[SkillScore, ...]`, in Skill order. A skill with no available component is omitted, and `score` is the unweighted mean of the available component scores.
- **Produces, in `domain/baseline_report.py`:**
  - `class CalibrationState(StrEnum)`: `NOT_RUN = "not_run"`, `SKIPPED = "skipped"`, `CALIBRATED = "calibrated"`.
  - `ClipRef(attempt_id: str, start_ms: int, end_ms: int, word: str | None, expected: str | None, produced: str | None)`.
  - `ReportItem`, with fields `error_key`, `description`, `skill`, `impact`, `p_hat`, `ci_low`, `ci_high`, `n_eff`, `status`, `priority`, `provisional` and `clips: tuple[ClipRef, ...]`.
  - `BaselineReport(session_id, completed_at, calibration: CalibrationState, scoring_config_id: str, snapshot_id: str, items: tuple[ReportItem, ...], skill_scores: tuple[SkillScore, ...], notes: tuple[str, ...])`.
  - `build_baseline_report(*, session_id, completed_at, profile: Profile, session_observations: Sequence[Observation], skill_scores, calibration: CalibrationState, scoring_config_id, snapshot_id, fillers_undercounted: bool, coach_scored: bool, max_clips: int = 3) -> BaselineReport`.

**Components and anchors.** These are config values, to be tuned after Phase 1.

| Skill | Component (value) | Score |
|---|---|---|
| Sounds | `accuracy`: mean Azure word accuracy over scored scripted words | the value |
| Sounds | `tracked_hit_share`: `1 − Σweight(miss) / Σweight` over sound-family observations | `100 × value` |
| On the spot | `median_first_word_ms` over quick answers with words | `linear_score(v, zero_at=5000, full_at=1000)` |
| On the spot | `fillers_per_min` over unscripted speech time (first word start to last word end) | `linear_score(v, zero_at=12, full_at=0)` |
| On the spot | `words_per_min`, excluding fillers | `linear_score(v, zero_at=60, full_at=150)` |
| On the spot | `mean_length_of_run`: words per run, with runs split at gaps ≥ 250 ms or at fillers | `linear_score(v, zero_at=2, full_at=12)` |
| On the spot | `grammar_errors_per_100_words` | `linear_score(v, zero_at=10, full_at=0)` |
| Articulate | `rubric`: mean of structure, clarity and concision (0–4) | `25 × value` |

**Report rules:**
- **Items:** one per profile entry whose key has at least one miss among `session_observations`. Ranked by the entry's `priority` descending, then by key.
- **Clips:** up to `max_clips` session misses of that key that have `start_ms` and `end_ms`, ordered by `(observed_at, start_ms)`.
- **Notes**, in this order, each only when it applies:
  - `Calibration was skipped: sound and prosody scores are provisional.` (state `SKIPPED`)
  - `Calibration hasn't been run: sound and prosody scores are provisional.` (`NOT_RUN`)
  - `Fillers may be undercounted: this transcriber drops filler words.`
  - `The coach was unavailable: grammar, structure and clarity were not scored.` (`not coach_scored`)

- [ ] **Step 1: Write the failing tests**

```python
# tests/domain/test_skill_scores.py
def test_linear_score_clamps(): assert [linear_score(v, zero_at=5000, full_at=1000) for v in (500, 3000, 6000)] == [100, 50, 0]
def test_sounds_score_averages_accuracy_and_hit_share():
    s = skill(SessionEvidence(scripted_pronunciation=(pa_result_with_word_accuracy(80),),
                              sound_observations=(miss(w=1.0), ok(w=1.0), ok(w=1.0), ok(w=1.0)), ...), Skill.SOUNDS)
    assert s.values == {"accuracy": 80, "tracked_hit_share": 0.75} and s.score == pytest.approx((80 + 75) / 2)
def test_on_the_spot_components(): ...      # hand-built transcripts -> exact values for each component
def test_articulate_from_rubric(): ...      # rubric 3, 2, 4 -> 75.0
def test_skill_without_evidence_is_omitted(): ...
```

```python
# tests/domain/test_baseline_report.py
def test_items_are_keys_missed_this_session_ranked_by_priority(): ...
def test_clips_point_at_the_users_misses(): ...       # ClipRef(attempt "a1", 100, 520, "vest", "v", "w"), at most 3
def test_provisional_flag_comes_from_the_profile_entry(): ...
def test_notes():
    r = report(calibration=CalibrationState.SKIPPED, fillers_undercounted=True, coach_scored=False)
    assert r.notes == ("Calibration was skipped: sound and prosody scores are provisional.",
                       "Fillers may be undercounted: this transcriber drops filler words.",
                       "The coach was unavailable: grammar, structure and clarity were not scored.")
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `uv run pytest tests/domain/test_skill_scores.py tests/domain/test_baseline_report.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement both modules** to the table and the rules above.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/domain -q && uv run pyright`
Expected: all pass.

- [ ] **Step 5: Commit, open the PR, merge when green**

```bash
git fetch origin && git switch -c p0e/09-skill-scores-report origin/main
git add apps/api docs/superpowers/HANDOFF.md
git commit -m "Add per-skill baseline scores and the ranked baseline report"
git push -u origin p0e/09-skill-scores-report && gh pr create --fill
gh pr checks --watch && gh pr merge --squash
```

---

### Task 10: The baseline session: API, completion and CLI

**Files:**
- Create:
  - `apps/api/src/nosolear/persistence/baseline_repository.py`
  - `apps/api/src/nosolear/ports/baseline_store.py`
  - `apps/api/src/nosolear/app/baseline.py`
  - `apps/api/src/nosolear/api/baseline_routes.py`, `api/baseline_schemas.py`
- Modify:
  - `persistence/repositories.py`: `ProfileRepository.snapshot` and `latest_snapshot`.
  - `ports/stores.py`: `ProfileWriter.snapshot`.
  - `app/scoring_steps.py`: `RescoreStep` refreshes completed baselines.
  - `api/deps.py`, `api/app.py`.
  - `first_run_cli.py`: `baseline start|status|complete|report`.
  - `tests/harness.py`.
  - `apps/web/src/shared/api/*` (regenerated).
- Test: `tests/persistence/test_baseline_repository.py`, `tests/app/test_baseline.py`, `tests/api/test_baseline_api.py`, `tests/test_cli_baseline.py`

**Interfaces:**
- **Consumes:**
  - Task 9: `skill_scores`, `SessionEvidence` and `build_baseline_report`.
  - Task 6: `SeedContent.protocol`.
  - Task 5: `ExtractionInputs`, `collect_results`, `rescore` and `RescoreStep`.
  - Task 2: `ObservationRepository.current` and `ScoringConfigReader`.
  - Task 8: `CalibrationStore.latest`.
  - `rebuild_profile` and `build_profile`.
- **Produces:**
  - **`ProfileRepository`:**
    - `snapshot(profile, *, session_id: str | None, reason: str) -> str` appends a snapshot without touching the entries.
    - `latest_snapshot(session_id: str, reason: str) -> tuple[str, Profile] | None` rebuilds entries from `entries_json` via `taxonomy.get`.
  - **`BaselineStore` (port) / `BaselineRepository(engine)`:**
    - `create(*, session_id, protocol: BaselineProtocol, now) -> None` creates the session (`kind="baseline"`, `protocol_version=protocol.version`) and one attempt per protocol item, in order, with `created_at = now + order µs`, `content_item_id`, the section's step, `scripted` for `read_aloud` and `word_list`, and `reference_text = item.text` only when scripted.
    - `open_session()` and `latest_completed()`, each returning `BaselineSessionRecord | None`.
    - `completed_sessions() -> list[BaselineSessionRecord]`.
    - `items(session_id) -> list[BaselineItemRecord]`.
    - `complete(session_id, *, completed_at) -> None`.
    - `save_scores(session_id, scores: Sequence[SkillScore]) -> None`, an upsert that stores `components_json = {"values": ..., "scores": ...}`.
    - `scores(session_id) -> tuple[SkillScore, ...]`.
  - **Records:**
    - `BaselineSessionRecord(id, protocol_version, started_at, completed_at)`.
    - `BaselineItemRecord(attempt_id, order, item_id, step, scripted, recorded: bool, job_status: str | None)`.
  - **`app/baseline.py`:**
    - Errors: `BaselinePending` and `BaselineNotOpen` (both `ValueError`).
    - `BaselineItemView(attempt_id, order, section, step, text, scripted, max_seconds, start_limit_seconds, stand_in_text, recorded, job_status)`, where `stand_in_text` is the text for a scripted item, else its `stand_in`.
    - `BaselineView(session: BaselineSessionRecord, items: tuple[BaselineItemView, ...])`.
    - `start_baseline(*, store, content, clock) -> BaselineView`: returns the open session if there is one.
    - `baseline_view(*, store, content) -> BaselineView | None`: the open session, else the latest completed one.
    - `complete_baseline(*, store, content, inputs, observations, profiles, configs, calibration, taxonomy, pack, clock) -> BaselineReport`:
      1. Raise `BaselineNotOpen` when no session is open.
      2. Raise `BaselinePending` unless every attempt is recorded and its analyze job is `done` or `failed`.
      3. `now = clock.now()`, then `rebuild_profile(..., session_id=id, reason="baseline")`.
      4. Gather `SessionEvidence` from the session's decoded analyses and current observations, then `save_scores(skill_scores(...))`.
      5. `complete(completed_at=now)`, then return `baseline_report(...)`.
    - `refresh_baseline(session_id: str, *, store, inputs, observations, profiles, taxonomy, pack) -> None`: `build_profile(current observations, as_of=completed_at)`, `profiles.snapshot(..., reason="baseline")`, then recompute and save the scores.
    - `refresh_completed_baselines(*, store, inputs, observations, profiles, taxonomy, pack) -> int`: calls `refresh_baseline` for every completed session and returns how many it refreshed.
    - `baseline_report(*, store, observations, profiles, configs, calibration, inputs) -> BaselineReport | None` reads the newest baseline snapshot of the latest completed session, its current observations and its scores.
  - **Report inputs:**
    - `calibration` is `CALIBRATED` when the newest config is calibrated, `SKIPPED` when the latest run is skipped, and otherwise `NOT_RUN`.
    - `fillers_undercounted` is true when any session transcript has `drops_fillers`.
    - `coach_scored` is true when any coach analysis exists for the session.
  - **`RescoreStep`** now runs `rescore(...)`, then `refresh_completed_baselines(...)`.
  - **Routes** (`BaselinePending` and `BaselineNotOpen` map to 409):
    - `POST /api/baseline` → 200 `BaselineSessionOut` (`startBaseline`).
    - `GET /api/baseline` → 200 `BaselineSessionOut`, or 404 (`getBaseline`).
    - `POST /api/baseline/complete` → 200 `BaselineReportOut` (`completeBaseline`).
    - `GET /api/baseline/report` → 200 `BaselineReportOut`, or 404 before completion (`getBaselineReport`).
  - **Schemas:**
    - `BaselineSessionOut`: `session_id`, `protocol_version`, `started_at`, `completed_at`, `items: list[BaselineItemOut]`.
    - `BaselineReportOut`: `session_id`, `completed_at`, `calibration`, `scoring_config_id`, `snapshot_id`, `items: list[ReportItemOut]` (with `clips: list[ClipOut]`), `skill_scores: list[SkillScoreOut]`, `notes: list[str]`.
    - `SkillScoreOut`: `skill`, `score`, `values: dict[str, float]`, `scores: dict[str, float]`.
  - **CLI:**
    - `nosolear baseline start` prints `{order:>3}  {attempt_id}  {section}  {text}`.
    - `status` prints the recorded count over the total.
    - `complete` and `report` print the ranked items, as `{n}. {description}  {p_hat:.0%} ({ci_low:.0%}–{ci_high:.0%})  n={n_eff:.0f}`, with a ` provisional` suffix where it applies. Then the skill scores and the notes.

**Safe 409 messages:**
- `BaselinePending`: `Record every baseline item and wait for its analysis to finish before completing.`
- `BaselineNotOpen`: `No baseline is in progress.`

- [ ] **Step 1: Write the failing tests**

```python
# tests/app/test_baseline.py
def test_start_creates_protocol_attempts_in_order(harness):
    view = start_baseline(...)
    assert [i.section for i in view.items] == ["read_aloud"] * N_SENTENCES + ["word_list"] * 4 + ["free_talk"] + ["rapid_questions"] * 5 + ["articulate"]
    assert all(i.scripted == (i.section in ("read_aloud", "word_list")) for i in view.items)
def test_start_returns_the_open_session(harness): ...
def test_complete_requires_every_item_settled(harness): ...          # one item unrecorded -> BaselinePending

def test_complete_writes_snapshot_scores_and_report(harness):
    record_all_baseline_items(harness, user_errors={"v": "w"}); harness.drain()
    report = complete_baseline(...)
    assert report.items[0].error_key == "sound.sub.v.w" and report.items[0].provisional
    assert report.items[0].clips and report.items[0].clips[0].attempt_id in baseline_attempt_ids(harness)
    assert {s.skill for s in report.skill_scores} == {Skill.SOUNDS, Skill.ON_THE_SPOT, Skill.ARTICULATE}
    assert snapshot_reasons(harness) == [("baseline", report.session_id)]
    assert "Calibration hasn't been run: sound and prosody scores are provisional." in report.notes

def test_report_is_none_before_completion(harness): ...

def test_rescore_refreshes_completed_baseline_report(harness):
    report = completed_baseline(harness, user_errors={"v": "w"})
    add_config(harness, CAL_CONFIG)                     # enables azure_pa for sound.sub.v.w
    harness.client.post("/api/rescore"); harness.drain()
    after = harness.client.get("/api/baseline/report").json()
    vw = next(i for i in after["items"] if i["error_key"] == "sound.sub.v.w")
    assert vw["provisional"] is False and after["snapshot_id"] != report.snapshot_id
    assert after["calibration"] == "calibrated"
```

```python
# tests/api/test_baseline_api.py
def test_baseline_endpoints(harness): ...                 # start 200, get 200, complete 409 while pending, report 404
def test_openapi_operation_ids(): ...
```

```python
# tests/test_cli_baseline.py
def test_cli_baseline_report_prints_ranked_items(harness, capsys): ...   # "1. /v/ said as /w/  " ... "provisional"
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `uv run pytest tests/app/test_baseline.py tests/api/test_baseline_api.py tests/test_cli_baseline.py tests/persistence/test_baseline_repository.py -q`
Expected: FAIL (`ModuleNotFoundError: nosolear.app.baseline`).

- [ ] **Step 3: Implement the repository, use cases, routes, schemas, CLI and the `RescoreStep` change** to the Interfaces block.

- [ ] **Step 4: Run the tests, regenerate the API types, and confirm they pass**

Run: `uv run pytest -q && uv run pyright && cd ../.. && make gen-api && make lint`
Expected: all pass; only `apps/web/src/shared/api/*` changes under `apps/web`.

- [ ] **Step 5: Commit, open the PR, merge when green**

```bash
git fetch origin && git switch -c p0e/10-baseline-session origin/main
git add apps/api apps/web/src/shared/api docs/superpowers/HANDOFF.md
git commit -m "Add the baseline session, skill scores and baseline report endpoints"
git push -u origin p0e/10-baseline-session && gh pr create --fill
gh pr checks --watch && gh pr merge --squash
```

---

### Task 11: Onboarding state and the end-to-end first run

**Files:**
- Create:
  - `apps/api/src/nosolear/domain/onboarding.py`
  - `apps/api/src/nosolear/app/onboarding.py`
  - `apps/api/src/nosolear/api/onboarding_routes.py`, `api/onboarding_schemas.py`
  - `apps/api/tests/e2e/test_first_run.py`
  - `apps/api/tests/live/test_first_run_live.py`
- Modify:
  - `first_run_cli.py`: `onboarding`, and `stand-in calibration|baseline`.
  - `cli.py`: `main(argv, *, client=None, synthesizer=None)`.
  - `api/deps.py`, `api/app.py`.
  - `tests/harness.py`: `make_harness(*, readiness: ReadinessReport | None = None, ...)` overrides `get_readiness_report`. The default is all components ready, with the phone probe `not_installed`.
  - `README.md`: the "First run" section.
  - `apps/web/src/shared/api/*` (regenerated).
- Test: `tests/domain/test_onboarding.py`, `tests/api/test_onboarding_api.py`, plus the e2e and live files above.

**Interfaces:**
- **Consumes:**
  - 0b: `ReadinessReport` and `ReadinessRow` from `get_readiness_report`.
  - Task 8: `CalibrationStore.latest`.
  - Task 10: `BaselineStore.open_session` and `latest_completed`.
  - 0d: `Synthesizer`, built for the CLI through `api/deps.py`.
  - 0c: `ApiClient.upload_wav` and `follow_job`.
- **Produces:**
  - **`domain/onboarding.py`:**
    - `class OnboardingStep(StrEnum)`: `READINESS = "readiness"`, `CALIBRATION = "calibration"`, `BASELINE = "baseline"`, `REPORT = "report"`, `DAILY_PLAN = "daily_plan"`.
    - `BLOCKING: Mapping[str, frozenset[str]]`, giving the component → statuses that block:
      - `azure_speech`, `anthropic`, `language_pack` and `data_dir`: everything except `ready`;
      - `azure_capabilities`: `missing` and `not_probed`;
      - `transcriber`: `missing` and `not_installed`.

      `phone_probe` and `usage` never block.
    - `readiness_blockers(report: ReadinessReport) -> tuple[str, ...]`, in row order.
    - `OnboardingFacts(blockers: tuple[str, ...], calibration: Literal["not_run", "running", "done", "skipped"], baseline: Literal["not_started", "open", "completed"], daily_sessions: int)`.
    - `next_step(f: OnboardingFacts) -> OnboardingStep`, checked in this order:
      1. Blockers → `READINESS`.
      2. Baseline completed → `DAILY_PLAN` if `daily_sessions > 0`, else `REPORT`.
      3. Calibration `not_run` or `running` → `CALIBRATION`.
      4. Otherwise → `BASELINE`.

      So a re-calibration after the baseline never sends onboarding back.
  - **`app/onboarding.py`:** `OnboardingState(step, blockers, calibration, baseline, baseline_session_id: str | None)` and `onboarding_state(*, readiness, calibration, baselines, daily_sessions: int) -> OnboardingState`. `daily_sessions` counts sessions with `kind = 'daily'`.
  - **`GET /api/onboarding`:** 200 `OnboardingOut` (`getOnboarding`), with fields `step`, `blockers: list[OnboardingBlockerOut(component, status, fix)]`, `calibration`, `baseline` and `baseline_session_id`. The `fix` copy comes from the readiness row.
  - **CLI:**
    - `first_run_cli.run(args, client, *, synthesizer: Synthesizer | None = None) -> int | None`. `cli.main` passes `synthesizer` through, or builds one through `api/deps.py` when it is `None`.
    - `nosolear onboarding` prints `Next: {step}`, then one hint line per step:
      - readiness: each blocker's fix;
      - calibration: `nosolear calibrate start (or nosolear calibrate skip)`;
      - baseline: `nosolear baseline start`;
      - report: `nosolear baseline report`;
      - daily_plan: `Daily practice arrives in Phase 1.`
    - `nosolear stand-in calibration|baseline` handles every unrecorded item of the running calibration run or the open baseline:
      - synthesizes `stand_in_text` through the metered, cached `Synthesizer` built by `api/deps.py`;
      - uploads the clip with `ApiClient.upload_wav`;
      - then follows every job and prints `Uploaded {n} stand-in recordings`.

      It exists so a first run can be driven with TTS audio standing in for a voice (§1, §13), and is documented in the README as a testing aid.

- [ ] **Step 1: Write the failing tests**

```python
# tests/domain/test_onboarding.py
@pytest.mark.parametrize("facts, step", [
    (F(blockers=("anthropic",)), OnboardingStep.READINESS),
    (F(), OnboardingStep.CALIBRATION),
    (F(calibration="running"), OnboardingStep.CALIBRATION),
    (F(calibration="skipped"), OnboardingStep.BASELINE),
    (F(calibration="done", baseline="open"), OnboardingStep.BASELINE),
    (F(calibration="done", baseline="completed"), OnboardingStep.REPORT),
    (F(calibration="running", baseline="completed"), OnboardingStep.REPORT),   # re-calibration doesn't reset
    (F(calibration="skipped", baseline="completed", daily_sessions=1), OnboardingStep.DAILY_PLAN),
])
def test_next_step(facts, step): assert next_step(facts) is step

def test_phone_probe_and_usage_never_block():
    assert readiness_blockers(report(phone_probe="not_installed", usage="degraded")) == ()
def test_unprobed_azure_blocks(): assert readiness_blockers(report(azure_capabilities="not_probed")) == ("azure_capabilities",)
```

```python
# tests/api/test_onboarding_api.py
def test_onboarding_reports_blockers_with_fixes(harness): ...    # readiness with anthropic missing -> step readiness
def test_onboarding_get_has_no_side_effects(harness): ...        # row counts of every table unchanged across 3 GETs
```

```python
# tests/e2e/test_first_run.py  (harness with committed content, readiness all ready, probe not installed, user_errors {"v": "w"})
def test_first_run_through_api_and_cli(harness, capsys):
    cli = lambda *argv: main(list(argv), client=ApiClient(http=harness.client), synthesizer=harness.voice.synthesizer)
    assert harness.client.get("/api/onboarding").json()["step"] == "calibration"
    assert cli("calibrate", "start") == 0 and cli("stand-in", "calibration") == 0
    assert cli("calibrate", "finish") == 0
    assert harness.client.get("/api/onboarding").json()["step"] == "baseline"
    assert cli("baseline", "start") == 0 and cli("stand-in", "baseline") == 0 and cli("baseline", "complete") == 0
    report = harness.client.get("/api/baseline/report").json()
    vw = next(i for i in report["items"] if i["error_key"] == "sound.sub.v.w")
    assert vw["provisional"] is False and vw["clips"]
    assert {s["skill"] for s in report["skill_scores"]} == {"sounds", "on_the_spot", "articulate"}
    assert harness.client.get("/api/onboarding").json()["step"] == "report"

def test_skip_then_calibrate_later_rescores_without_provider_calls(harness):
    ...  # calibrate skip -> baseline (v.w provisional) -> calibrate start, stand-in, finish;
         # record voice.calls and ledger_rows() after the calibrate job's evaluate step, then drain the rescore job:
         # both unchanged by the rescore, the baseline observations' current config is the calibrated one,
         # and the report's v.w item is no longer provisional
```

```python
# tests/live/test_first_run_live.py
@pytest.mark.live
def test_first_run_on_tts_audio(live_harness):
    ...  # the same flow as test_first_run_through_api_and_cli with the real adapters and a 2-key calibration set
         # (v.w and f.p), on a temporary data dir sharing the user's ledger; asserts the run completes, a calibrated
         # config exists and the baseline report has skill scores. Excluded by default; run via make test-live.
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `uv run pytest tests/domain/test_onboarding.py tests/api/test_onboarding_api.py tests/e2e -q`
Expected: FAIL (`ModuleNotFoundError: nosolear.domain.onboarding`).

- [ ] **Step 3: Implement onboarding, the route, the CLI commands, and the README "First run" section**

The README section covers `nosolear onboarding` → `calibrate start` / `skip` → `upload` → `calibrate finish` → `baseline start` → `upload` → `baseline complete` → `baseline report`. It adds a note that `stand-in` spends TTS characters and Azure audio, like any recording.

- [ ] **Step 4: Run the full suite, regenerate the API types, and confirm they pass**

Run: `uv run pytest -q && uv run pyright && cd ../.. && make gen-api && make test && make lint`
Expected: all pass, with the e2e tests among them. The live test is collected but deselected.

- [ ] **Step 5: Commit, open the PR, merge when green**

```bash
git fetch origin && git switch -c p0e/11-onboarding-first-run origin/main
git add apps/api apps/web/src/shared/api README.md docs/superpowers/HANDOFF.md
git commit -m "Add onboarding state and an end-to-end first run through the API and CLI"
git push -u origin p0e/11-onboarding-first-run && gh pr create --fill
gh pr checks --watch && gh pr merge --squash
```

---

### Task 12: Phase 0e verification, security review and handoff

**Files:**
- Modify: `docs/superpowers/HANDOFF.md`; `docs/ARCHITECTURE.md` (§13 Phase 0e marked done with the date).

- [ ] **Step 1: Run the whole-phase checks**

Run: `git fetch origin && git switch -c p0e/12-phase-verification origin/main && make test && make lint && HYPOTHESIS_PROFILE=heavy uv --directory apps/api run pytest tests/domain -q`
Expected: all pass. Hypothesis `heavy` reports no falsifying examples.

- [ ] **Step 2: Check the contract and hygiene**

Run: `make gen-api && git diff --exit-code apps/web && git ls-files | bash scripts/check-no-personal-data.sh`
Expected: no diff, and hygiene exits 0.

- [ ] **Step 3: List the live tests (do not run them without keys)**

Run: `uv --directory apps/api run pytest -m live --collect-only -q`
Expected: the list includes `tests/live/test_first_run_live.py::test_first_run_on_tts_audio`. Record it in HANDOFF.md as unverified until the owner runs `make test-live` with keys.

- [ ] **Step 4: Run `/security-review` on the phase's merged changes and fix any finding in this branch**

Check in particular:
- coach issues can't reach SQL or paths (Task 4's injection tests);
- every calibration control call goes through the metered ports;
- re-scoring has no provider port;
- no 0e response or job `steps_json` can carry a key (planted-key tests);
- every new GET is side-effect free.

- [ ] **Step 5: Mark the phase done and hand off**

Update HANDOFF.md: Phase 0e done, Phase 1 next, and the open owner questions. Mark §13 Phase 0e done in ARCHITECTURE.md with the date.

```bash
git add docs/superpowers/HANDOFF.md docs/ARCHITECTURE.md
git commit -m "Mark Phase 0e done after verification and security review"
git push -u origin p0e/12-phase-verification && gh pr create --fill
gh pr checks --watch && gh pr merge --squash
```

---

## Done when

- A first run driven through the API and CLI goes from readiness, through calibration (or a skip), to a baseline report:
  - with fakes, in `tests/e2e/test_first_run.py` (CI);
  - with TTS audio, in `tests/live/test_first_run_live.py` (`make test-live`, with the owner's keys).
- Re-scoring after calibration changes earlier observations without any provider call or ledger use (`test_skip_then_calibrate_later_rescores_without_provider_calls`).
- `make test` and `make lint` pass, and the `contract` check shows no drift.

## Cross-phase assumptions

Each line gives what this plan assumes and which phase must produce it. Where a neighbouring plan names something differently, its name wins and this plan's tasks follow it.

- **0b:**
  - `LanguagePack` in `nosolear/domain/packs.py` with `id`, `hypotheses: Mapping[str, str]` and `calibration_emphasis: tuple[str, ...]`.
  - `load_pack(content_dir, pack_id)`, and `get_pack()` in `api/deps.py`.
  - `tests/factories.py` exports `PACK` (the neutral pack).
- **0b:** `build_profile(observations, *, as_of, taxonomy, pack, config=DEFAULT_CONFIG)` and `rebuild_profile(*, observations, profiles, taxonomy, pack, clock, config)`, with `profile_entries.pack_id`.
- **0b:** `CONTENT_DIR = REPO_ROOT / "content"` in `settings.py`, and the 78 salvaged calibration items committed under `content/calibration/` (Task 6 converts them to its shape if needed).
- **0b:**
  - `ReadinessReport(rows: tuple[ReadinessRow, ...])`, with `ReadinessRow(component: str, status: str, reason: str, fix: str | None)`.
  - Statuses: `ready`, `missing`, `not_installed`, `not_probed`, `degraded`.
  - Component ids: `azure_speech`, `azure_capabilities`, `anthropic`, `transcriber`, `phone_probe`, `language_pack`, `data_dir`, `usage`.
  - Served by `get_readiness_report()` in `api/deps.py`.
- **0b:** the `live` marker, `make test-live`, and a `live_harness`-style fixture: a temporary data dir that shares the user's ledger.
- **0c:**
  - Tables `recordings`, `jobs` and `analyses` per §7.
  - `analyses.attempt_id` is NOT NULL, with unique `(attempt_id, kind)` and no `tts_hash` or `calibration_run_id` yet.
  - `jobs.kind` has a CHECK limited to `analyze` and `rescore`; `jobs.attempt_id` is nullable.
- **0c:**
  - A job step registry: steps have `name`, `needs`, `applies(job)` and `run(job)`, and a job context gives `attempt_id` and `progress(fraction)`.
  - Job kinds are registered in `api/deps.py`, and `JobQueue.enqueue(kind, *, attempt_id=None) -> str`.
  - Typed step errors `CapExceeded`, `ProviderUnavailable`, `CapabilityMissing` and `InvalidAudio`.
  - A test-only synchronous drain of queued jobs.
- **0c:**
  - `JobAcceptedOut(job_id: str)` and `GET /api/jobs/{id}` with a `status` field.
  - `ApiClient` (httpx, runtime dependency) with `get_json`, `post_json`, `upload_wav(attempt_id, path) -> job_id` and `follow_job(job_id)`.
  - `cli.main(argv, *, client: ApiClient | None = None)`, and the CLI command `nosolear upload <attempt_id> <wav>`.
- **0c–0d:** migration heads `0003` (0b), `0004` (0c), `0005` (0d), so 0e's migration is `0006`.
- **0d:** `tts_cache.hash` is the table's primary key.
- **0d** (`nosolear/domain/provider_results.py`):
  - `RawAnalysis(kind, provider, provider_version, adapter, adapter_version, raw)`.
  - Pure `decode(RawAnalysis) -> PronunciationResult | Transcript | PhoneProbeResult | CoachResult`, raising `ValueError` on bad input.
  - `encode(result, *, provider, provider_version, adapter, adapter_version) -> RawAnalysis` (used by fakes).
  - The analysis kinds `pronunciation`, `transcript`, `phone_probe` and `coach`.
- **0d, fields 0e reads:**
  - `PronunciationResult`: `words`, `has_nbest`, `has_prosody`.
  - `PaWord`: `text`, `start_ms`, `end_ms`, `accuracy`, `error_type` (Azure's ErrorType verbatim), `phonemes`, `unexpected_break`, `missing_break`, `monotone`.
  - `PaPhoneme`: `phone` (Azure en-US IPA), `accuracy`, `start_ms`, `end_ms`, `nbest: tuple[PhoneCandidate(phone, score), ...]`.
  - `Transcript`: `words: tuple[TimedWord(text, start_ms, end_ms), ...]`, `drops_fillers`.
  - `PhoneProbeResult`: `words: tuple[ProbeWord(text, expected, ops, start_ms | None, end_ms | None), ...]`, with `ProbeOp(kind: "match" | "sub" | "ins" | "del", expected, heard, position)`.
  - `CoachResult`: `issues: tuple[CoachIssue(error_key, quote | None), ...]` and `rubric: CoachRubric(structure, clarity, concision) | None` (0–4 each; present for `articulate`).
- **0d:**
  - Ports `PronunciationScorer.score(audio: Path, *, reference_text: str | None) -> RawAnalysis`, `PhoneProbe.probe(audio: Path, *, reference_text: str) -> RawAnalysis` and `Synthesizer.synthesize(text: str, *, rate: float = 1.0) -> SynthesizedClip(hash, path, ...)`.
  - Step classes for score, transcribe, probe and coach, whose `applies` 0e amends.
  - `create_app(settings, *, providers: ProviderPorts | None = None)`. It wraps the given raw ports as cache → retry → metered, so fakes are metered too.
  - A builder in `api/deps.py` the CLI can use for the `Synthesizer`.
  - `tests/fakes.py` with `FakeCoach`.
- **0d:** the latest `azure_pa` `provider_capabilities` row exposes `nbest`, `prosody` and `provider_version`, and the readiness `phone_probe` row is `ready` only when the `local` extra and espeak-ng are installed.

## Produces for later phases

- **`domain/scoring.py`:** `ScoringConfig`, `ScoringConfig.rule_for(detector, definition) -> ScoringRule | None`, `V0_CONFIG`, `V0_CONFIG_ID = "v0"`, `enabled_keys(...)`, `current_observations(...)`. `Observation.scoring_config_id` / `.provisional` and `ProfileEntry.provisional`.
- **`domain/extraction/extract.py`:** `extract(item: ExtractionItem, results: ProviderResults, *, config, pack, taxonomy) -> dict[Detector, tuple[Observation, ...]]`. This is what Phase 1's daily attempts and Phase 3's drills go through.
- **`app/extract_attempt.py`:** `extract_attempt(*, attempt_id, inputs, configs, extractions, pack, taxonomy, clock) -> ExtractSummary` and `collect_results(analyses)`.
- **`app/rescore.py`:** `rescore(*, inputs, configs, extractions, observations, profiles, pack, taxonomy, clock, on_progress) -> RescoreSummary`.
- **Job kinds:** `rescore` (via `POST /api/rescore`) and `calibrate`. Analyze jobs end with the `extract` step.
- **Rebuilding:** `rebuild_profile(..., session_id=None, reason="rebuild")`, where `reason=None` replaces the entries without a snapshot. `ProfileRepository.snapshot(...)` and `latest_snapshot(session_id, reason)`.
- **`ObservationRepository.current()`:** the observations the profile uses, meaning the newest config per attempt.
- **`domain/content.py`:** `ContentItem`, `ContentKind`, `SeedContent`, `BaselineProtocol` (reused by Phase 5's re-test, with passage A and the same word list), and `ContentRepository.sync_seed`.
- **`domain/skill_scores.py`:** `skill_scores(SessionEvidence) -> tuple[SkillScore, ...]`, and the `skill_scores` table written per session (Phase 1 writes the daily ones).
- **`domain/baseline_report.py`:** `BaselineReport`, `ReportItem`, `ClipRef`, `CalibrationState`.
- **Onboarding:** `OnboardingStep` and `GET /api/onboarding` (`getOnboarding`). Phase 1 makes `daily_plan` real; until it exists, a completed baseline leads to `report`.
- **Endpoints:** `startCalibration`, `getCalibration`, `skipCalibration`, `finishCalibration`, `startBaseline`, `getBaseline`, `completeBaseline`, `getBaselineReport`, `startRescore`, `getOnboarding`. All are typed in `apps/web/src/shared/api/schema.d.ts` for Phase 2.
- **CLI:** `nosolear rescore`, `calibrate start|status|skip|finish`, `baseline start|status|complete|report`, `onboarding`, `stand-in calibration|baseline`.
- **Test doubles:** `tests/oracle_voice.py` (`OracleVoice`) and `tests/harness.py` (`harness` fixture), for Phase 1's API tests.
