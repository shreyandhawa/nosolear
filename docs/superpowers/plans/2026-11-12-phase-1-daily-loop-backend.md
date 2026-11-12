# Phase 1: Daily Loop Backend: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After a baseline, today's daily session is planned from the error profile (Thompson-sampling selection policy), its recording flows through the existing upload → job → extraction → profile path, and the session yields one feedback item per skill; tomorrow's plan visibly reflects today's misses. All of it runs with fakes through the API and the CLI.

**Architecture:** Three new pure domain modules (`selection`, `rechecks`, `daily_plan`, plus `feedback`) make every decision; use cases in `app/` orchestrate them over new Protocol ports; SQLite repositories and FastAPI routes are thin adapters. The feedback explanation is the only new paid call: it goes through the `Coach` port built by the composition root (cache → retry → metered → raw), its output is untrusted and sanitized in the domain, and any typed failure degrades to written templates with a recorded reason, never silently.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy Core + Alembic (SQLite), Hypothesis, pytest, uv. No new third-party dependencies (random draws use the stdlib `random.Random.betavariate`, hashing uses `hashlib`).

**Spec:** [docs/ARCHITECTURE.md](../../ARCHITECTURE.md), mainly §13 (Phase 1), §6.5–§6.7, §7, §8, §11, §15.

## Global Constraints

- **Python:** 3.14, uv with `uv.lock`. Any new dependency is pinned with `==` and the lockfile updated. Heavy local-model deps stay in the optional extras `local` and `apple` (§3); adapters import them lazily. Phase 1 adds none.
- **Commands** (from `apps/api`): `uv run pytest -q`, `uv run ruff check`, `uv run ruff format --check`, `uv run pyright` (strict for `src`). From the repo root: `make test`, `make lint`, `make gen-api`.
- **TDD for every change:** failing test first, run it, minimal code, run it, commit.
- **Architecture rules:** the `domain` package has no I/O. Adapters are chosen only in the composition root `apps/api/src/nosolear/api/deps.py`. Every port has a fake in tests, in the style of `tests/factories.py`. Use cases take keyword-only constructor-style dependencies; domain errors are `ValueError` subclasses; docstrings explain why.
- **Hypothesis** properties for domain logic. Profiles: `default` 100 examples, `heavy` 1000 via `HYPOTHESIS_PROFILE=heavy`.
- **Live tests** are marked `@pytest.mark.live`, excluded by default, run by `make test-live` (0b). CI never has keys. Phase 1 adds one live test (the real coach explaining three fixes), listed in HANDOFF, not run without keys.
- **Hygiene:** never commit audio or anything under `data/`. Fixtures are synthetic and contain no real person's voice. `scripts/check-no-personal-data.sh` runs in CI and pre-commit.
- **apps/web:** the only permitted change is regenerating API types with `make gen-api` (commit the regenerated files) whenever the OpenAPI changes, so the CI `contract` check stays green.
- **Security (owner's rules):** keys come only from env or `.env` and never appear in logs, API responses, error messages, OpenAPI examples or fixtures. Bind to 127.0.0.1, restrict CORS to the app origin, never expose the API unauthenticated. Treat transcripts and coach output as untrusted; use structured outputs with the taxonomy enum; model output never reaches a file path, shell command or SQL string. Check the usage ledger before every paid call (a bug must not burn quota). No telemetry. Document exactly what is sent to which provider. No GET changes state or triggers a paid call (§15), so plan and feedback creation are `POST`.
- **Values from the spec:** re-check spacing 2, 4, 8, 16, 32 days (§6.6); a focus can't win more than 3 days in a row unless its sampled score is at least double the runner-up's (§6.6); exactly one focus per skill and one fix per skill (§6.6, §6.7); daily Claude cap is per day in UTC (§11); typed errors `InvalidAudio`, `CapExceeded`, `ProviderUnavailable`, `CapabilityMissing` (§8.1); session protocol times from §8.2.
- **Delivery recipe (every task):** one branch `p1/NN-<slug>` from up-to-date `origin/main` (`git fetch origin && git switch -c <branch> origin/main`), test-first commits pushed as you go (`git push -u origin <branch>`). Commit messages: an imperative sentence, **no** `Co-Authored-By` trailer, **no** "Generated with Claude Code" footer. Never push to main. Each task's PR also updates `docs/superpowers/HANDOFF.md` (done / in progress / next, and the adapters still unverified against the live service). Open the PR with `gh pr create`, and when CI is green merge with `gh pr merge --squash` and **without** `--delete-branch` (the owner approves branch deletions).
- **Migrations:** other phases add Alembic revisions too. Each migration task sets `down_revision` to the single current head (`uv run alembic heads` from `apps/api`, after rebasing on `origin/main`), uses batch mode for SQLite, and adds a schema test in `tests/persistence/test_schema.py` style.

## Review Focus

The inputs most likely to bite that the spec implies but the obvious tests skip. Each has a pinned test in its owning task.

1. **Day rollover.** A user outside UTC (Nepal is +05:45) will call the plan endpoint around the UTC day boundary. §11 fixes UTC, so the plan for a date must be created once, stay frozen when the profile changes later that day, and a call after UTC midnight must create the next day's plan. Task 4 (`test_same_utc_day_returns_frozen_plan`, `test_next_utc_day_builds_new_plan`).
2. **Brand-new or empty profile, empty content bank.** A skipped baseline or fresh install must still produce a plan (one fallback focus per skill, `prompt=None`) instead of a 500. Task 1 (`test_empty_profile_still_has_one_focus_per_skill`), Task 3 (`test_empty_prompt_bank_gives_no_prompt`).
3. **Feedback asked for before the analysis job finishes.** Returning partial feedback built from half the observations would be wrong and sticky. Expect 409 `session_not_analyzed`, and no coach call. Task 8 (`test_unfinished_job_refuses_without_calling_coach`), Task 9 (API 409).
4. **Coach capped, down or hostile.** `CapExceeded`/`ProviderUnavailable`, an explanation for a key that was not asked about, a 50 kB message, control or bidi characters, or a missing item must each yield a stored template item with a visible `fallback_reason`; a later request after recovery upgrades it once and never re-calls the coach for items already written by it. Task 7 (`test_hostile_explanations_are_rejected`), Task 8 (`test_capped_coach_stores_template_with_reason`, `test_second_request_upgrades_template_items_only`).
5. **A skill with nothing to fix.** A session with no misses for a skill ("clean") is different from a skill that was not scored at all (Azure missing or capped, "not scored today"); inventing a card for either is wrong. Task 7 (`test_clean_and_not_scored_are_distinct`).

## Not in This Plan

- Drill content and drill screens (Phase 3), the web screens (Phase 2), the weekly re-test (Phase 5). The plan only names drill families (`DrillSpec`); no drill attempts are created.
- Coach-written prompts for tomorrow (§6.6 step 4 "or written by the coach"). Phase 1 picks from the seed content bank only, which is also the §8.2 fallback; Phase 3 fills the bank from the coach.
- Model-voice audio for feedback cards (Phase 2 asks the TTS cache). Phase 1 returns `model_text` only.
- A timezone setting. The day is the UTC date (§11).

## File Map

```
apps/api/src/nosolear/
  domain/selection.py          select(), Focus, RecheckProbe, Selection, seed_for_date, SelectionConfig
  domain/rechecks.py           RecheckState, RECHECK_DAYS, advance_rechecks
  domain/daily_plan.py         DailyPlan, PromptCandidate, DrillSpec, PlanStep, PLAN_STEPS, choose_prompt, assemble_plan
  domain/feedback.py           choose_fixes, SkillOutcome, FixChoice, sanitize_explanation, template_explanation, errors
  ports/plan.py                ProfileReader, RecheckStore, PromptBank, ScoredKeys, DailyPlanStore, StoredPlan
  ports/feedback.py            StoredObservation, SessionObservationReader, SessionJobStatus, SessionReader, FeedbackStore
  app/build_daily_plan.py      get-or-create today's plan
  app/start_daily_session.py   session + speak attempt for today's plan
  app/generate_feedback.py     choose fixes, ask coach, sanitize, fall back, persist
  app/complete_daily_session.py  rebuild + snapshot, advance re-checks
  persistence/models.py        daily_plans, feedback_items, profile_entries/sessions columns
  persistence/migrations/versions/<rev>_*.py   one per schema task
  persistence/repositories.py  (or plan_repositories.py / feedback_repositories.py) new repos
  api/plan_routes.py           /api/plan/today, /api/plan/today/session, /api/sessions/{id}/feedback|complete
  api/schemas.py               PlanOut, FocusOut, DailySessionOut, FeedbackOut, ...
  cli.py                       `nosolear plan`, `nosolear daily start|feedback|complete|run`
apps/api/tests/                mirrors src/ (domain/, app/, persistence/, api/, test_cli.py, e2e/test_daily_loop.py)
```

---

### Task 1: Selection policy (pure domain)

**Branch:** `p1/01-selection-policy`

**Files:**
- Create: `apps/api/src/nosolear/domain/selection.py`
- Test: `apps/api/tests/domain/test_selection.py`, `apps/api/tests/domain/test_selection_properties.py`
- Modify: `apps/api/tests/factories.py` (add `entry(...)` helper)

**Interfaces:**
- Consumes: `Profile`, `ProfileEntry`, `prior_for` (`domain/profile.py`), `BetaState`, `KeyEstimate` (`domain/estimates.py`), `Status`, `Skill`, `Taxonomy`, `KeyDefinition`. **Assumes** 0e added `ProfileEntry.provisional: bool` with default `False`; this task reads it.
- Consumes (declared here, implemented in Task 2): `RecheckState` (`domain/rechecks.py`: `@dataclass(frozen=True, slots=True) RecheckState(stage: int, next_at: datetime)`). To avoid a cycle, define `RecheckState` in this task's PR inside `domain/rechecks.py` with only that dataclass; Task 2 adds the rest.
- Produces (`domain/selection.py`):
  - `SKILL_ORDER: tuple[Skill, ...] = (Skill.SOUNDS, Skill.ON_THE_SPOT, Skill.ARTICULATE)`
  - `@dataclass(frozen=True, slots=True) SelectionConfig(max_streak: int = 3, streak_ratio: float = 2.0, focus_statuses: frozenset[Status] = frozenset({Status.ACTIVE, Status.IMPROVING, Status.UNKNOWN}))`, `DEFAULT_SELECTION`
  - `@dataclass(frozen=True, slots=True) Focus(skill: Skill, error_key: str, impact: int, status: Status, p_hat: float, sampled_rate: float, score: float, runner_up_score: float | None, provisional: bool, source: Literal["profile", "fallback"])`
  - `@dataclass(frozen=True, slots=True) RecheckProbe(skill: Skill, error_key: str, due_at: datetime)`
  - `@dataclass(frozen=True, slots=True) Selection(foci: tuple[Focus, ...], probe: RecheckProbe | None)`
  - `seed_for_date(day: date) -> int` (first 8 bytes of `sha256(day.isoformat())`, big-endian; never Python `hash()`)
  - `select(*, profile: Profile | None, taxonomy: Taxonomy, seed: int, now: datetime, history: Mapping[Skill, Sequence[str]], rechecks: Mapping[str, RecheckState], is_scored: Callable[[str], bool], config: SelectionConfig = DEFAULT_SELECTION) -> Selection`. `history[skill]` is the previous plans' focus keys, most recent first. `now` must be timezone-aware (`ValueError` otherwise).

**Rules to implement (ARCHITECTURE.md §6.6, with the decisions this plan makes):**
1. Per skill, candidates are profile entries of that skill whose status is in `focus_statuses` and `is_scored(key)`. Mastered keys never become focus; a mastered key whose `rechecks[key].next_at <= now` and that is scored is a re-check probe candidate.
2. Score = `Random(f"{seed}:{key}").betavariate(a, b) * impact`, one independent generator per key, so the result does not depend on entry order or on which other keys exist. Highest score wins; ties break by key.
3. Variety: if the winner equals each of the last `max_streak` keys in `history[skill]` and `score < streak_ratio * runner_up_score`, the runner-up is focus instead. `Focus.runner_up_score` records the runner-up's score (or `None`).
4. Fallback: a skill with no profile candidate draws from `taxonomy.defined()` keys of that skill that are not in the profile and are scored, sampled from their prior (`prior_for`, status `UNKNOWN`, `source="fallback"`). A skill with an empty pool gets no focus.
5. Probe: at most one in total; highest impact, then earliest `due_at`, then key. A probe key is never also a focus.
6. Keys that are not scored (`is_scored` false: a "drilled but not scored" key, §6.8) are never focus or probe, so the plan never asks the user to improve something the app cannot measure.

- [ ] **Step 1: Write the failing example tests** in `tests/domain/test_selection.py`, using a new `factories.entry(key, *, a, b, status, provisional=False, at=NOW) -> ProfileEntry` (builds the estimate with `estimate()` and `priority=p_hat*impact`):
  - `test_seed_for_date_is_stable_and_distinct`: `seed_for_date(date(2026,11,12))` equals a hard-coded integer (compute once and paste), differs for the next day.
  - `test_confident_high_impact_wins_most_days`: keys `sound.sub.v.w` (impact 3, a=30, b=70) and a low-impact weak key (a=3, b=7); over seeds 0..199 the first wins more than 60% and the second wins at least once.
  - `test_one_focus_per_skill_in_skill_order`
  - `test_mastered_and_watching_are_never_focus`
  - `test_due_mastered_key_is_probe_not_focus` and `test_not_yet_due_mastered_key_is_not_probe`
  - `test_unscored_key_is_never_selected` (`is_scored=lambda k: k != "sound.sub.v.w"` with that key the clear leader)
  - `test_streak_of_three_blocks_winner_unless_double`: history `[k, k, k]` makes the runner-up the focus; give the leader a sampled score at least double the runner-up (a=90,b=2 vs a=2,b=90) and it stays.
  - `test_empty_profile_still_has_one_focus_per_skill`: `profile=None` gives three `source="fallback"` foci, all scored, all `UNKNOWN`.
  - `test_naive_now_is_rejected`
  - `test_provisional_flag_is_carried`

- [ ] **Step 2: Run to verify they fail**

Run: `cd apps/api && uv run pytest tests/domain/test_selection.py -q`
Expected: FAIL (`ModuleNotFoundError: nosolear.domain.selection`).

- [ ] **Step 3: Implement** `domain/selection.py` and the `RecheckState` dataclass in `domain/rechecks.py` per the rules above. Docstring on `select` explains why per-key generators are used (order independence and stable plans when unrelated keys appear).

- [ ] **Step 4: Run the example tests**

Run: `cd apps/api && uv run pytest tests/domain/test_selection.py -q`
Expected: PASS.

- [ ] **Step 5: Write the Hypothesis properties** in `tests/domain/test_selection_properties.py`. Strategy `profiles`: a dict of 0..12 keys drawn from `DEFAULT_TAXONOMY.defined()`, each with `a, b` floats in `[1, 80]` and a random `Status`, built with `factories.entry`. Properties, each over random `seed`, `history`, `rechecks` and a random unscored subset:
  - `test_determinism`: same arguments give an equal `Selection`; reversing or shuffling the entries gives an equal `Selection`.
  - `test_at_most_one_focus_per_skill_and_exactly_one_when_pool_nonempty`: foci skills are distinct and in `SKILL_ORDER`; every skill with a non-empty scored pool (profile candidates or fallback) has a focus.
  - `test_focus_is_scored_and_of_its_skill_and_focusable`: `is_scored(f.error_key)`, `taxonomy.get(key).skill == f.skill`, status in `focus_statuses` (profile) or `UNKNOWN` (fallback), never `MASTERED`/`WATCHING`.
  - `test_variety_rule`: if `history[skill][:3]` are all equal to `k`, then `focus.error_key != k` or `focus.runner_up_score is None` or `focus.score >= 2 * focus.runner_up_score`.
  - `test_probe_is_due_scored_mastered_and_not_a_focus`
  - `test_different_dates_vary`: across 50 consecutive dates the focus for a profile with two comparable active sound keys is not constant.

- [ ] **Step 6: Run the properties, then the full gate**

Run: `cd apps/api && uv run pytest tests/domain -q && HYPOTHESIS_PROFILE=heavy uv run pytest tests/domain/test_selection_properties.py -q && uv run ruff check && uv run ruff format --check && uv run pyright`
Expected: all PASS / clean.

- [ ] **Step 7: Deliver** (recipe in Global Constraints; branch `p1/01-selection-policy`; HANDOFF note: selection done).

---

### Task 2: Re-check schedule (domain, persistence, carry-forward)

**Branch:** `p1/02-recheck-schedule`

**Files:**
- Modify: `apps/api/src/nosolear/domain/rechecks.py`, `persistence/models.py`, `persistence/repositories.py`
- Create: `persistence/migrations/versions/<rev>_recheck_columns.py`, `apps/api/src/nosolear/ports/plan.py` (only `RecheckStore` in this task)
- Test: `tests/domain/test_rechecks.py`, `tests/persistence/test_recheck_store.py`

**Interfaces:**
- Consumes: `RecheckState` (Task 1), `Profile`, `Status`.
- Produces:
  - `RECHECK_DAYS: tuple[int, ...] = (2, 4, 8, 16, 32)`
  - `advance_rechecks(*, profile: Profile, previous: Mapping[str, RecheckState], checked: AbstractSet[str], now: datetime) -> dict[str, RecheckState]`:
    - a mastered key with no previous state starts at `RecheckState(stage=0, next_at=now + RECHECK_DAYS[0] days)`;
    - a mastered key in `checked` (it had at least one opportunity in the session just completed) moves to `stage=min(stage+1, 4)` with `next_at = now + RECHECK_DAYS[new_stage] days`;
    - a mastered key not in `checked` keeps its previous state;
    - a key that is not mastered is dropped (a relapse restarts at stage 0 when it is mastered again).
  - `ports/plan.py`: `class RecheckStore(Protocol): def load(self) -> dict[str, RecheckState]; def save(self, states: Mapping[str, RecheckState]) -> None`
  - `persistence`: `RecheckRepository(engine)` implementing `RecheckStore`; new nullable column `profile_entries.next_recheck_at` (UTCDateTime, per §7) and `profile_entries.recheck_stage` (Integer, nullable; an addition to §7 that the reviewer must reconcile). `ProfileRepository.save` carries both columns forward for keys that are still in the new profile with status `mastered` (it currently deletes and reinserts every row, which would otherwise wipe the schedule on every rebuild).

- [ ] **Step 1: Write failing domain tests** in `tests/domain/test_rechecks.py`: `test_newly_mastered_starts_at_two_days`, `test_checked_key_advances_through_2_4_8_16_32_then_stays_at_32` (loop 7 checks, assert the day gaps `[2,4,8,16,32,32,...]` after the first), `test_unchecked_key_keeps_state`, `test_relapsed_key_is_dropped_and_restarts_at_stage_zero`. Plus a Hypothesis property `test_next_at_is_always_in_the_future_of_now_and_stage_is_bounded`.

- [ ] **Step 2: Run to verify they fail.** Run: `uv run pytest tests/domain/test_rechecks.py -q`. Expected: FAIL (`advance_rechecks` missing).

- [ ] **Step 3: Implement `advance_rechecks`** in `domain/rechecks.py` (pure; no clock reads).

- [ ] **Step 4: Run to verify pass.** Same command. Expected: PASS.

- [ ] **Step 5: Write failing persistence tests** in `tests/persistence/test_recheck_store.py` using the `db_engine` fixture: `test_save_then_load_roundtrip`; `test_profile_save_carries_schedule_for_still_mastered_keys` (save a profile with a mastered key, `RecheckRepository.save`, call `ProfileRepository.save` with a rebuilt profile still mastering the key, `load()` returns the same state); `test_profile_save_drops_schedule_when_key_no_longer_mastered`; `test_schema_has_recheck_columns` (nullable).

- [ ] **Step 6: Run to verify they fail.** Run: `uv run pytest tests/persistence/test_recheck_store.py -q`. Expected: FAIL.

- [ ] **Step 7: Implement** the migration (batch add of two nullable columns), the `models.py` columns, `RecheckRepository`, and the carry-forward inside the existing transaction of `ProfileRepository.save` (read the old `error_key, next_recheck_at, recheck_stage` before `delete`).

- [ ] **Step 8: Run the full gate.** Run: `cd apps/api && uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run pyright`. Expected: PASS / clean.

- [ ] **Step 9: Deliver** (branch `p1/02-recheck-schedule`).

---

### Task 3: Daily plan assembly (pure domain)

**Branch:** `p1/03-daily-plan-domain`

**Files:**
- Create: `apps/api/src/nosolear/domain/daily_plan.py`
- Test: `tests/domain/test_daily_plan.py`, `tests/domain/test_daily_plan_properties.py`

**Interfaces:**
- Consumes: `Selection`, `Focus`, `RecheckProbe`, `SKILL_ORDER` (Task 1); `Taxonomy`.
- Produces (`domain/daily_plan.py`):
  - `PLAN_PROTOCOL_VERSION = 1`
  - `class StepKind(StrEnum): SPEAK="speak"; ANALYZE="analyze"; FEEDBACK="feedback"; DRILL="drill"; LOG="log"`
  - `@dataclass(frozen=True, slots=True) PlanStep(kind: StepKind, skill: Skill | None, duration_s: int)`
  - `PLAN_STEPS: tuple[PlanStep, ...]` (§8.2): speak 60, analyze 45, feedback 90, drill sounds 240, drill on_the_spot 180, drill articulate 180, log 0, in that order.
  - `@dataclass(frozen=True, slots=True) PromptCandidate(id: str, text: str, target_keys: tuple[str, ...])`
  - `@dataclass(frozen=True, slots=True) DrillSpec(skill: Skill, error_key: str, drill_family: str)` (family from `KeyDefinition.drill_family`)
  - `@dataclass(frozen=True, slots=True) DailyPlan(for_date: date, seed: int, foci: tuple[Focus, ...], probe: RecheckProbe | None, prompt: PromptCandidate | None, drills: tuple[DrillSpec, ...], steps: tuple[PlanStep, ...], protocol_version: int)`
  - `choose_prompt(candidates: Sequence[PromptCandidate], selection: Selection, *, seed: int, recent_ids: Sequence[str] = ()) -> PromptCandidate | None`: density = number of focus keys in `target_keys` (weight 1.0) plus 0.5 if the probe key is in it; highest wins; ties and the all-zero case break with `Random(seed)` over the sorted ids (deterministic); ids in `recent_ids` are excluded unless that would leave no candidate; empty input gives `None`.
  - `assemble_plan(*, for_date: date, selection: Selection, prompts: Sequence[PromptCandidate], recent_prompt_ids: Sequence[str], taxonomy: Taxonomy) -> DailyPlan` (seed from `seed_for_date`; `drills` has one `DrillSpec` per focus, so at most 3; at most one probe).

- [ ] **Step 1: Write the failing tests** in `tests/domain/test_daily_plan.py`: `test_prompt_with_most_focus_keys_wins`, `test_probe_key_adds_half_weight`, `test_recent_prompts_are_avoided_when_alternatives_exist`, `test_recent_prompts_allowed_when_only_choice`, `test_empty_prompt_bank_gives_no_prompt`, `test_steps_match_protocol_times` (total of durations equals 60+45+90+240+180+180 s), `test_drills_follow_focus_and_use_taxonomy_drill_family`, `test_plan_for_same_date_is_identical`.

- [ ] **Step 2: Run to verify they fail.** Run: `uv run pytest tests/domain/test_daily_plan.py -q`. Expected: FAIL (module missing).

- [ ] **Step 3: Implement** the module per the signatures above.

- [ ] **Step 4: Run to verify pass.** Same command. Expected: PASS.

- [ ] **Step 5: Add Hypothesis properties** in `tests/domain/test_daily_plan_properties.py`: `test_caps` (at most 3 foci and drills, at most 1 probe, at most 1 prompt, for any selection), `test_prompt_comes_from_the_bank`, `test_assemble_is_deterministic`.

- [ ] **Step 6: Run the gate.** Run: `cd apps/api && uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run pyright`. Expected: PASS / clean.

- [ ] **Step 7: Deliver** (branch `p1/03-daily-plan-domain`).

---

### Task 4: `build_daily_plan` use case and `daily_plans` persistence

**Branch:** `p1/04-build-daily-plan`

**Files:**
- Create: `app/build_daily_plan.py`, `persistence/migrations/versions/<rev>_daily_plans.py`, `adapters`-free repositories in `persistence/plan_repositories.py`
- Modify: `ports/plan.py`, `persistence/models.py`, `api/deps.py`
- Test: `tests/app/test_build_daily_plan.py`, `tests/persistence/test_daily_plan_repository.py`

**Interfaces:**
- Consumes: Tasks 1–3; `ProfileRepository.latest() -> Profile | None`; `Clock`; `DEFAULT_TAXONOMY`. **Assumes (0e):** table `content_items(id, kind, text, target_keys, source, retired_at)` with `target_keys` stored as JSON text (a list of strings), and a scoring config exposing `ScoringConfig.scores_key(error_key: str) -> bool` read through `ScoringConfigRepository.latest() -> ScoringConfig` (0e).
- Produces (`ports/plan.py`):
  - `class ProfileReader(Protocol): def latest(self) -> Profile | None`
  - `class PromptBank(Protocol): def prompts(self) -> list[PromptCandidate]` (non-retired `kind='prompt'` items)
  - `class ScoredKeys(Protocol): def is_scored(self, error_key: str) -> bool`
  - `@dataclass(frozen=True, slots=True) StoredPlan(id: str, plan: DailyPlan)`
  - `class DailyPlanStore(Protocol): def get(self, for_date: date) -> StoredPlan | None; def add(self, plan: DailyPlan) -> StoredPlan; def recent_focus_keys(self, before: date, limit: int = 3) -> dict[Skill, list[str]]; def recent_prompt_ids(self, before: date, limit: int = 3) -> list[str]` where `add` returns the already-stored plan if `for_date` exists (the `UNIQUE(for_date)` constraint decides races).
  - `build_daily_plan(*, plans: DailyPlanStore, profiles: ProfileReader, rechecks: RecheckStore, prompts: PromptBank, scoring: ScoredKeys, taxonomy: Taxonomy, clock: Clock) -> StoredPlan`. The date is `clock.now().astimezone(UTC).date()` (§11: periods are UTC). It returns the stored plan unchanged if one exists for that date, otherwise selects, assembles, stores and returns it.
  - Table `daily_plans(id TEXT PK, for_date TEXT UNIQUE NOT NULL, focus_json TEXT, prompt_item_id TEXT NULL FK content_items.id, drills_json TEXT, seed INTEGER)` (§7). `drills_json` is an object `{"probe": ..., "drills": [...], "prompt": {"id","text","target_keys"} | null, "protocol_version": 1}` so the plan stays reproducible when a content item is later retired. `DailyPlanRepository(engine, taxonomy)` implements the store; `PromptBankRepository(engine)`; `ScoringCoverage(scoring_configs)` adapter implements `ScoredKeys` over 0e's latest scoring config (when no config row exists, every key is scored, matching a fresh `v0`).
  - `api/deps.py`: `get_build_daily_plan(request) -> Callable[[], StoredPlan]` style dependency, or individual `get_*` providers, following the existing `get_profile_repository` pattern.

- [ ] **Step 1: Write failing repository tests** (`tests/persistence/test_daily_plan_repository.py`, `db_engine` fixture): `test_add_then_get_roundtrips_the_plan_exactly`, `test_second_add_for_same_date_returns_first_plan`, `test_recent_focus_keys_are_most_recent_first_and_per_skill`, `test_recent_prompt_ids_excludes_today_and_later`, `test_schema_unique_for_date`, `test_prompt_bank_skips_retired_and_non_prompt_items`.

- [ ] **Step 2: Run to verify they fail.** Run: `uv run pytest tests/persistence/test_daily_plan_repository.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement** the migration, table, repositories and `ScoringCoverage`; JSON round-trip of `Focus`/`DrillSpec`/`PromptCandidate` lives in the repository with explicit (de)serializers, not pickle.

- [ ] **Step 4: Run to verify pass.** Same command. Expected: PASS.

- [ ] **Step 5: Write failing use-case tests** in `tests/app/test_build_daily_plan.py` with in-memory fakes (`FakeDailyPlanStore`, `FakeRecheckStore`, `FakePromptBank`, `FakeScoredKeys`, `FixedClock` from factories, a mutable clock for day advance):
  - `test_same_utc_day_returns_frozen_plan`: build, then add misses to the profile fake, build again at a later time the same UTC day: the stored plan object is returned unchanged.
  - `test_next_utc_day_builds_new_plan`: a clock at `2026-11-12T23:50Z` then `2026-11-13T00:10Z` gives two different `for_date`s; the user's local date (`NPT`) is irrelevant.
  - `test_streak_history_feeds_selection`: three stored plans with the same sounds focus plus a profile where it narrowly leads produce a different focus.
  - `test_recent_prompts_are_not_repeated`
  - `test_empty_prompt_bank_gives_no_prompt` and `test_no_profile_builds_fallback_plan`
  - `test_unscored_keys_are_not_selected` (fake `ScoredKeys`)
  - `test_probe_comes_from_due_rechecks`

- [ ] **Step 6: Run to verify they fail.** Run: `uv run pytest tests/app/test_build_daily_plan.py -q`. Expected: FAIL.

- [ ] **Step 7: Implement `build_daily_plan`** in `app/build_daily_plan.py` and the deps providers.

- [ ] **Step 8: Run the gate.** Run: `cd apps/api && uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run pyright`. Expected: PASS / clean.

- [ ] **Step 9: Deliver** (branch `p1/04-build-daily-plan`).

---

### Task 5: Plan API and CLI

**Branch:** `p1/05-plan-api-cli`

**Files:**
- Create: `api/plan_routes.py`
- Modify: `api/schemas.py`, `api/app.py` (include router), `cli.py`, regenerated `apps/web/src/shared/api/openapi.json` and `schema.d.ts` (`make gen-api`)
- Test: `tests/api/test_plan_api.py`, `tests/test_cli.py` (new cases)

**Interfaces:**
- Consumes: `build_daily_plan`, `DailyPlanStore` (Task 4); **assumes (0c)** the CLI HTTP helper `nosolear.cli_client.ApiClient` with `get_json(path) -> Any` and `post_json(path, body=None) -> Any`, constructed from an `httpx.Client`, and `cli.main(argv, *, client: ApiClient | None = None)` so tests can inject `TestClient`-backed transport.
- Produces:
  - `POST /api/plan/today` (operation id `buildTodayPlan`): builds or returns today's plan; 201 on creation, 200 when it already existed. Body is `PlanOut`.
  - `GET /api/plan/today` (`getTodayPlan`): 200 `PlanOut`, or 404 `{"detail": "no_plan_for_today"}`. Side-effect free (§15).
  - `PlanOut(id: str, for_date: date, seed: int, protocol_version: int, foci: list[FocusOut], probe: ProbeOut | None, prompt: PromptOut | None, drills: list[DrillOut], steps: list[StepOut])`; `FocusOut(skill, error_key, description, impact, status, p_hat, provisional, source)`; `ProbeOut(skill, error_key, due_at)`; `PromptOut(id, text, target_keys)`; `DrillOut(skill, error_key, drill_family)`; `StepOut(kind, skill, duration_s)`. Sampled scores stay out of the API.
  - CLI: `nosolear plan [--json]` posts to `/api/plan/today` and prints one line per focus (`sounds: sound.sub.v.w (active, 31%)`), the probe, the prompt text and the step list; `--json` prints the response body.

- [ ] **Step 1: Write failing API tests** in `tests/api/test_plan_api.py` using `client_with_tmp_db` plus a seeded profile (`seeded_profile`): `test_get_before_post_is_404`, `test_post_creates_then_returns_same_plan` (201 then 200, equal bodies), `test_get_after_post_matches`, `test_get_has_no_side_effects` (row count of `daily_plans` unchanged after GET), `test_plan_has_one_focus_per_skill`, `test_empty_db_still_returns_a_plan` (fallback foci), `test_response_fields_exact` (set of keys per object).

- [ ] **Step 2: Run to verify they fail.** Run: `uv run pytest tests/api/test_plan_api.py -q`. Expected: FAIL (404 on routes).

- [ ] **Step 3: Implement** the schemas and routes; mapping lives in a `_plan_out(StoredPlan, taxonomy)` helper.

- [ ] **Step 4: Run to verify pass.** Same command. Expected: PASS.

- [ ] **Step 5: Write failing CLI tests** in `tests/test_cli.py`: `test_plan_prints_one_line_per_skill`, `test_plan_json_flag_prints_the_body`, `test_plan_is_idempotent_across_two_runs`.

- [ ] **Step 6: Run to verify they fail, then implement** the `plan` subcommand through the injected `ApiClient`. Run: `uv run pytest tests/test_cli.py -q`. Expected after implementing: PASS.

- [ ] **Step 7: Regenerate the contract and run everything.** Run: `make gen-api && make test && make lint`. Expected: green; `git status` shows only the regenerated web API files plus this task's files.

- [ ] **Step 8: Deliver** (branch `p1/05-plan-api-cli`).

---

### Task 6: Daily session start (wiring the recording path)

**Branch:** `p1/06-daily-session-start`

**Files:**
- Create: `app/start_daily_session.py`, `persistence/migrations/versions/<rev>_sessions_plan_id.py`
- Modify: `ports/plan.py`, `persistence/models.py`, `persistence/plan_repositories.py`, `api/plan_routes.py`, `api/schemas.py`, `cli.py`, regenerated web API files
- Test: `tests/app/test_start_daily_session.py`, `tests/api/test_daily_session_api.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `build_daily_plan` (Task 4). **Assumes (0e):** `attempts.content_item_id` (nullable FK to `content_items`); **(0c):** `POST /api/attempts/{id}/recording` (raw `audio/wav`) and `GET /api/jobs/{id}`, whose job runs score → transcribe → probe → coach → extract → profile rebuild for the attempt, and the CLI `ApiClient.upload_wav(attempt_id: str, path: Path) -> str` (returns the job id) and `ApiClient.follow_job(job_id: str) -> dict[str, Any]` (blocks until a terminal state).
- Produces:
  - Column `sessions.plan_id TEXT NULL REFERENCES daily_plans(id)` with a unique index (one daily session per plan).
  - `@dataclass(frozen=True, slots=True) AttemptRef(id: str, step: str, reference_text: str | None, content_item_id: str | None)` and `StartedSession(session_id: str, plan_id: str, created: bool, attempts: tuple[AttemptRef, ...])`.
  - `class DailySessionStore(Protocol): def for_plan(self, plan_id: str) -> StartedSession | None; def create(self, *, plan_id: str, prompt_item_id: str | None, started_at: datetime) -> StartedSession`
  - `start_daily_session(*, build_plan: Callable[[], StoredPlan], sessions: DailySessionStore, clock: Clock) -> StartedSession`: builds or fetches today's plan, then gets or creates the session: `sessions(kind='daily', protocol_version=PLAN_PROTOCOL_VERSION, plan_id, started_at)` with exactly one attempt `step='speak'`, `scripted=False`, `reference_text=None`, `content_item_id=<plan prompt id>`. The attempt is what 0c's upload and 0e's extraction already understand, so the daily recording travels the same path as baseline recordings.
  - `POST /api/plan/today/session` (`startDailySession`): 201 on creation, 200 on repeat; body `DailySessionOut(session_id, plan_id, attempts: list[AttemptOut(id, step, prompt_text: str | None)])`.
  - CLI: `nosolear daily start` prints the session id, the attempt id and the prompt text.

- [ ] **Step 1: Write failing use-case tests** (`tests/app/test_start_daily_session.py`, fakes for `DailySessionStore`): `test_creates_one_speak_attempt_with_prompt_item`, `test_repeat_returns_same_session_and_attempt`, `test_plan_without_prompt_gives_null_content_item`.

- [ ] **Step 2: Write failing API tests** (`tests/api/test_daily_session_api.py`): `test_first_post_201_then_200_same_ids`, `test_creates_plan_if_missing`, `test_attempt_row_is_unscripted_speak_with_content_item` (query the DB), `test_session_row_kind_daily_with_plan_id`, `test_unique_plan_id_index_rejects_second_session` (schema).

- [ ] **Step 3: Run to verify they fail.** Run: `uv run pytest tests/app/test_start_daily_session.py tests/api/test_daily_session_api.py -q`. Expected: FAIL.

- [ ] **Step 4: Implement** the migration (batch add of `plan_id` and the unique index on SQLite), the repository `DailySessionRepository(engine)`, the use case, the route and schemas.

- [ ] **Step 5: Run to verify pass.** Same command. Expected: PASS.

- [ ] **Step 6: Write and pass CLI tests** (`test_daily_start_prints_attempt_and_prompt`, `test_daily_start_twice_prints_same_ids`), implement `daily start`.

- [ ] **Step 7: Regenerate the contract and run everything.** Run: `make gen-api && make test && make lint`. Expected: green.

- [ ] **Step 8: Deliver** (branch `p1/06-daily-session-start`).

---

### Task 7: Feedback logic (pure domain)

**Branch:** `p1/07-feedback-domain`

**Files:**
- Create: `apps/api/src/nosolear/domain/feedback.py`, `apps/api/src/nosolear/ports/feedback.py` (only `StoredObservation` in this task)
- Test: `tests/domain/test_feedback.py`, `tests/domain/test_feedback_properties.py`

**Interfaces:**
- Consumes: `Observation`, `Outcome`, `Profile`, `Taxonomy`, `Skill`, `Family`, `KeyDefinition`, `SKILL_ORDER`. **Assumes (0e)** observation `evidence` holds `word: str` (the expected word, when there is one), `quote: str` (the quoted words, for coach-judged keys), `start_ms`/`end_ms` ints (§6.3).
- Produces:
  - `ports/feedback.py`: `@dataclass(frozen=True, slots=True) StoredObservation(id: int, observation: Observation)`
  - `domain/feedback.py`:
    - `class SkillState(StrEnum): FIX="fix"; CLEAN="clean"; NOT_SCORED="not_scored"`
    - `@dataclass(frozen=True, slots=True) FixChoice(skill: Skill, error_key: str, observation_id: int, attempt_id: str | None, word: str | None, quote: str | None, start_ms: int | None, end_ms: int | None, priority: float)`
    - `@dataclass(frozen=True, slots=True) SkillOutcome(skill: Skill, state: SkillState, fix: FixChoice | None)`
    - `choose_fixes(*, session_observations: Sequence[StoredObservation], profile: Profile, taxonomy: Taxonomy) -> tuple[SkillOutcome, ...]`: always three outcomes in `SKILL_ORDER`. Per skill: no observations for the skill gives `NOT_SCORED`; observations but no miss gives `CLEAN`; otherwise `FIX` for the missed key with the highest current profile `priority` (a key missing from the profile uses `1.0 * impact`), ties by key; the evidence observation is that key's miss with the highest weight, ties by earliest `observed_at`, then lowest id. The domain picks, never the LLM (§6.7).
    - `@dataclass(frozen=True, slots=True) RawExplanation(error_key: str, message: str, model_text: str | None)` is **owned by 0d** (`ports/coach.py`); `sanitize_explanation` accepts any object with those three attributes through a local `Protocol`.
    - `@dataclass(frozen=True, slots=True) Explanation(error_key: str, message: str, model_text: str | None)`
    - `MAX_MESSAGE_CHARS = 400`, `MAX_MODEL_TEXT_CHARS = 300`
    - `sanitize_explanation(raw: ExplanationLike | None, *, fix: FixChoice, taxonomy: Taxonomy) -> Explanation | None`: `None` unless `raw.error_key == fix.error_key`; control characters (Unicode categories `Cc`, `Cf`, which includes bidi overrides) are removed and whitespace collapsed; empty or over-length message gives `None`; `model_text` is kept only for grammar, structure and clarity keys (the coach rewrite) and also length-capped, for sound and prosody keys it is replaced with `fix.word`, and for fluency keys it is `None`. Text is returned as plain text (never escaped here; the UI renders text, §15).
    - `template_explanation(fix: FixChoice, taxonomy: Taxonomy) -> Explanation`: a written template per family, mentioning the description and (when present) the word or quote; the same `model_text` rule as above. Must work for every defined key and every dynamic sound key.
    - Typed errors (all `ValueError` subclasses): `SessionNotFound`, `SessionNotDaily`, `SessionNotAnalyzed`.
    - `FallbackReason` literal: `"cap_exceeded" | "provider_unavailable" | "capability_missing" | "invalid_output"`.

- [ ] **Step 1: Write the failing example tests** in `tests/domain/test_feedback.py` (build `StoredObservation`s with `factories.mk`):
  - `test_picks_highest_priority_missed_key_per_skill`
  - `test_evidence_is_highest_weight_miss_of_that_key`
  - `test_clean_and_not_scored_are_distinct` (sounds: only `ok` observations gives CLEAN; no sound observations gives NOT_SCORED)
  - `test_outcomes_always_three_in_skill_order`
  - `test_ties_break_by_key`
  - `test_sanitize_accepts_matching_explanation_and_strips_controls` (`"fix‮ it\x00"` becomes `"fix it"`)
  - `test_hostile_explanations_are_rejected` parametrized: other key than the fix, message of 50,000 chars, empty message, `None`
  - `test_sound_model_text_comes_from_domain_not_coach` (coach says `model_text="rm -rf /"`, result equals `fix.word`)
  - `test_coach_rewrite_kept_for_grammar_and_capped`
  - `test_template_exists_for_every_defined_key` (loop `DEFAULT_TAXONOMY.defined()` plus `sound.sub.θ.s`-style dynamic key)

- [ ] **Step 2: Run to verify they fail.** Run: `uv run pytest tests/domain/test_feedback.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement** `domain/feedback.py` and `StoredObservation`.

- [ ] **Step 4: Run to verify pass.** Same command. Expected: PASS.

- [ ] **Step 5: Add Hypothesis properties** (`tests/domain/test_feedback_properties.py`): `test_at_most_one_fix_per_skill_and_it_is_a_session_miss`, `test_fix_key_belongs_to_its_skill`, `test_sanitized_text_has_no_control_chars_and_respects_caps` (random unicode strings), `test_choose_fixes_is_order_independent`.

- [ ] **Step 6: Run the gate.** Run: `cd apps/api && uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run pyright`. Expected: PASS / clean.

- [ ] **Step 7: Deliver** (branch `p1/07-feedback-domain`).

---

### Task 8: `generate_feedback` use case and `feedback_items` persistence

**Branch:** `p1/08-generate-feedback`

**Files:**
- Create: `app/generate_feedback.py`, `persistence/feedback_repositories.py`, `persistence/migrations/versions/<rev>_feedback_items.py`
- Modify: `ports/feedback.py`, `persistence/models.py`, `persistence/repositories.py` (add `ObservationRepository.for_session`), `api/deps.py`, `PRIVACY.md` (the 0b file), `tests/fakes` additions
- Test: `tests/app/test_generate_feedback.py`, `tests/persistence/test_feedback_repository.py`, `tests/persistence/test_repositories.py` (new `for_session` cases)

**Interfaces:**
- Consumes: Task 7; `Coach`, `FixRequest`, `RawExplanation` from **0d** (`nosolear/ports/coach.py`). **Assumed shape:** `class Coach(Protocol): def explain_fixes(self, fixes: Sequence[FixRequest]) -> Sequence[RawExplanation]`, `FixRequest(error_key: str, description: str, word: str | None, quote: str | None)`. If 0d named it differently, change only the `_ask_coach` helper in this task. **Assumes (0c/0d)** typed errors `CapExceeded`, `ProviderUnavailable`, `CapabilityMissing` importable from `nosolear.domain.errors`, and that `api/deps.py` builds `Coach` as cache → retry → metered → raw so the ledger reserve happens inside the call.
- Produces:
  - Columns on `feedback_items` (§7 has `id, session_id, skill, error_key, observation_id, message, model_text`) plus `source TEXT CHECK IN ('coach','template')`, `fallback_reason TEXT NULL CHECK IN ('cap_exceeded','provider_unavailable','capability_missing','invalid_output')`, `created_at`; `UNIQUE(session_id, skill)`; `observation_id` FK to `observations.id`. (`source` and `fallback_reason` are Phase 1 additions to §7 to be reconciled.)
  - `ports/feedback.py`:
    - `class SessionReader(Protocol): def kind(self, session_id: str) -> str | None` (None means no such session)
    - `class SessionJobStatus(Protocol): def unfinished(self, session_id: str) -> int` (queued, running, or failed jobs of the session's attempts; failed counts because partial observations would give wrong feedback until the job is resumed)
    - `class SessionObservationReader(Protocol): def for_session(self, session_id: str) -> list[StoredObservation]`
    - `@dataclass(frozen=True, slots=True) FeedbackItem(id: str, session_id: str, skill: Skill, error_key: str, observation_id: int, attempt_id: str | None, start_ms: int | None, end_ms: int | None, word: str | None, message: str, model_text: str | None, source: Literal["coach","template"], fallback_reason: FallbackReason | None)`
    - `class FeedbackStore(Protocol): def for_session(self, session_id: str) -> list[FeedbackItem]; def upsert(self, session_id: str, items: Sequence[FeedbackItem]) -> None`
    - `@dataclass(frozen=True, slots=True) SkillFeedback(skill: Skill, state: SkillState, item: FeedbackItem | None)` and `FeedbackReport(session_id: str, skills: tuple[SkillFeedback, ...], degraded: bool)` (`degraded` true when any item is a template)
  - `generate_feedback(*, session_id: str, sessions: SessionReader, jobs: SessionJobStatus, observations: SessionObservationReader, profiles: ProfileReader, feedback: FeedbackStore, coach: Coach, taxonomy: Taxonomy) -> FeedbackReport`:
    1. `SessionNotFound` if no session; `SessionNotDaily` if kind is not `daily`; `SessionNotAnalyzed` if `jobs.unfinished(...) > 0`. These checks run before any coach call.
    2. `choose_fixes` over the session's observations and the latest profile (an empty profile is allowed).
    3. If every chosen fix already has a `source='coach'` item, return the stored report without calling the coach (idempotent). Otherwise ask the coach in **one** `explain_fixes` call only for fixes that lack a coach item (at most 3, one request, bounded text: `quote` and `word` truncated to 300 chars).
    4. Per fix, `sanitize_explanation`; a `None`, a missing item or a coach item for an unrequested key becomes `template_explanation` with `fallback_reason="invalid_output"`.
    5. Catch only `CapExceeded`, `ProviderUnavailable`, `CapabilityMissing` around the coach call: every fix gets a template item with the matching reason. Any other exception propagates (no blanket `except`).
    6. Upsert and return the report. Stored coach items are never downgraded by a later template.
  - `ObservationRepository.for_session(session_id) -> list[StoredObservation]` (joins `observations.attempt_id` to `attempts.session_id`, ordered by `observed_at, id`), `SessionJobRepository`, `SessionRepository.kind`, `FeedbackRepository`.
  - `PRIVACY.md`: add under the Anthropic row: the feedback call sends, per fix, the error key and its short description plus the quoted words or expected word (each at most 300 characters). No audio and no full transcript.

- [ ] **Step 1: Write failing repository tests**: `test_for_session_only_returns_that_sessions_observations_with_ids` (two sessions), `test_feedback_upsert_replaces_by_session_and_skill`, `test_feedback_roundtrip_keeps_source_and_reason`, `test_check_constraints_reject_bad_source_and_reason`, `test_unfinished_counts_queued_running_and_failed_jobs` (insert jobs rows with the 0c schema).

- [ ] **Step 2: Run to verify they fail.** Run: `uv run pytest tests/persistence -q`. Expected: FAIL.

- [ ] **Step 3: Implement** migration, tables and repositories.

- [ ] **Step 4: Run to verify pass.** Same command. Expected: PASS.

- [ ] **Step 5: Write failing use-case tests** in `tests/app/test_generate_feedback.py` with `FakeCoach` (records calls, scripted results or raised errors), in-memory fakes of the new ports:
  - `test_one_item_per_skill_with_misses_and_coach_text`
  - `test_unfinished_job_refuses_without_calling_coach` (`SessionNotAnalyzed`, `coach.calls == []`)
  - `test_unknown_and_non_daily_sessions_raise_typed_errors`
  - `test_single_batched_coach_call_for_at_most_three_fixes`
  - `test_capped_coach_stores_template_with_reason` (`CapExceeded` gives `source='template'`, `fallback_reason='cap_exceeded'`, `degraded=True`); same for `ProviderUnavailable` and `CapabilityMissing`
  - `test_hostile_coach_output_falls_back_to_template_invalid_output`
  - `test_unexpected_exception_propagates` (`RuntimeError` is not swallowed)
  - `test_second_request_does_not_call_coach_when_all_items_are_coach`
  - `test_second_request_upgrades_template_items_only` (first call capped, second succeeds: the coach is asked only for the template fixes; coach-written items are untouched)
  - `test_clean_skill_has_no_item_and_no_coach_request`
  - `test_planted_key_never_appears_in_stored_text` (coach raising an error whose message contains a fake key: nothing stored contains it)

- [ ] **Step 6: Run to verify they fail, then implement** `generate_feedback`. Run: `uv run pytest tests/app/test_generate_feedback.py -q`. Expected after implementing: PASS.

- [ ] **Step 7: Run the gate.** Run: `cd apps/api && uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run pyright`. Expected: PASS / clean. Add `@pytest.mark.live` test `tests/live/test_claude_explain_fixes_live.py` (real wrapped coach, synthetic fix, asserts a sanitized explanation comes back); it must be skipped by default (`uv run pytest -q` still green).

- [ ] **Step 8: Deliver** (branch `p1/08-generate-feedback`; HANDOFF lists `claude_coach.explain_fixes` as unverified live).

---

### Task 9: Feedback API and CLI

**Branch:** `p1/09-feedback-api-cli`

**Files:**
- Modify: `api/plan_routes.py` (or new `api/feedback_routes.py` included in `api/app.py`), `api/schemas.py`, `api/deps.py`, `cli.py`, regenerated web API files
- Test: `tests/api/test_feedback_api.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `generate_feedback`, `FeedbackStore`, `FeedbackReport` (Task 8); `ApiClient` (0c).
- Produces:
  - `POST /api/sessions/{session_id}/feedback` (`generateFeedback`): the only call that can reach the coach. 200 with `FeedbackOut`. Errors: 404 `{"detail": "session_not_found"}`, 409 `{"detail": "session_not_daily"}` and `{"detail": "session_not_analyzed"}` (fixed safe strings; no provider text).
  - `GET /api/sessions/{session_id}/feedback` (`getFeedback`): side-effect free; 404 `feedback_not_generated` when no items were ever stored for the session, else 200 `FeedbackOut`.
  - `FeedbackOut(session_id: str, degraded: bool, skills: list[SkillFeedbackOut])`; `SkillFeedbackOut(skill: Literal["sounds","on_the_spot","articulate"], state: Literal["fix","clean","not_scored"], item: FeedbackItemOut | None)`; `FeedbackItemOut(id, error_key, message, model_text: str | None, source: Literal["coach","template"], fallback_reason: str | None, attempt_id: str | None, start_ms: int | None, end_ms: int | None, word: str | None)`.
  - CLI: `nosolear daily feedback SESSION_ID [--generate]` (without the flag it GETs, with it POSTs) prints one card per skill (`not scored today`, `clean`, or the fix with `[template: cap_exceeded]` when degraded).

- [ ] **Step 1: Write failing API tests** (`tests/api/test_feedback_api.py`; override the coach dependency with `FakeCoach`, seed a daily session with finished fake jobs and observations):
  - `test_post_returns_three_skill_cards_with_fixes`
  - `test_post_before_job_finished_is_409_session_not_analyzed_and_coach_untouched`
  - `test_get_before_generate_is_404` and `test_get_has_no_side_effects` (coach call count and row count unchanged)
  - `test_unknown_session_is_404` and `test_baseline_session_is_409_not_daily`
  - `test_capped_coach_returns_200_degraded_with_reason`
  - `test_post_twice_is_idempotent`
  - `test_response_and_openapi_contain_no_planted_key` (set a planted `NOSOLEAR_ANTHROPIC_API_KEY`, have the fake coach raise an error mentioning it, assert it is absent from the body, the logs captured by `caplog`, and `app.openapi()`); also add the two new routes to 0d's planted-key route sweep if it exists.
  - `test_hostile_coach_text_is_returned_as_plain_text_without_control_chars`

- [ ] **Step 2: Run to verify they fail.** Run: `uv run pytest tests/api/test_feedback_api.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement** the routes, schemas, error-to-status mapping (a small dict, no message passthrough) and deps providers.

- [ ] **Step 4: Run to verify pass.** Same command. Expected: PASS.

- [ ] **Step 5: Write and pass CLI tests** (`test_daily_feedback_prints_card_per_skill`, `test_daily_feedback_shows_degraded_reason`, `test_daily_feedback_without_generate_reports_not_generated`), implement `daily feedback`.

- [ ] **Step 6: Regenerate the contract and run everything.** Run: `make gen-api && make test && make lint`. Expected: green.

- [ ] **Step 7: Deliver** (branch `p1/09-feedback-api-cli`).

---

### Task 10: Complete the session and run the whole daily loop end to end

**Branch:** `p1/10-complete-session-e2e`

**Files:**
- Create: `app/complete_daily_session.py`, `tests/e2e/test_daily_loop.py`
- Modify: `app/rebuild_profile.py` (accept `session_id` and `reason`), `ports/stores.py`, `api/plan_routes.py`, `api/schemas.py`, `cli.py`, regenerated web API files
- Test: `tests/app/test_complete_daily_session.py`, `tests/app/test_rebuild_profile.py`, `tests/api/test_complete_api.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: Tasks 1–9; `advance_rechecks`, `RecheckStore`, `SessionJobStatus`, `ObservationRepository`, `ProfileRepository`. **Assumes (0c/0d/0e):** fakes `FakePronunciationScorer`, `FakeTranscriber`, `FakeCoach`, a synchronous way to run queued jobs in tests (`JobRunner.run_pending()` or the app's test hook), a synthetic WAV factory in `tests/audio.py`, and a 0e extraction that turns the fakes' canned results into observations on `sound.sub.v.w`, `fluency.filler`, `grammar.article`.
- Produces:
  - `rebuild_profile(..., session_id: str | None = None, reason: str = "rebuild")` (backwards compatible; existing callers and `test_rebuild_profile.py` unchanged).
  - `complete_daily_session(*, session_id: str, sessions: SessionReader, sessions_writer: SessionCompleter, jobs: SessionJobStatus, observations: SessionObservationReader, all_observations: ObservationReader, profiles: ProfileWriter, rechecks: RecheckStore, taxonomy: Taxonomy, clock: Clock) -> CompletedSession`, with `class SessionCompleter(Protocol): def completed_at(self, session_id: str) -> datetime | None; def complete(self, session_id: str, at: datetime) -> None` and `CompletedSession(session_id: str, completed_at: datetime, already_completed: bool)`. Order: typed checks (`SessionNotFound`, `SessionNotDaily`, `SessionNotAnalyzed`); if `completed_at` is already set, return `already_completed=True` and change nothing (so re-calling can't advance re-check stages twice); otherwise rebuild and snapshot the profile with `reason="daily"` and this `session_id` (§6.8), then `advance_rechecks` with `checked` = keys that have at least one observation in this session, `rechecks.save`, `complete`.
  - `POST /api/sessions/{session_id}/complete` (`completeDailySession`): 200 `CompleteOut(session_id, completed_at, already_completed)`; errors as in Task 9.
  - CLI: `nosolear daily complete SESSION_ID`; `nosolear daily run WAV [--no-generate]`: `start` → `ApiClient.upload_wav` → `ApiClient.follow_job` (stop with a non-zero exit and the job's safe error if it ends `failed`) → `POST feedback` → print cards → `complete`. The feedback step is the only one that can reach the coach.

- [ ] **Step 1: Write failing use-case tests** (`tests/app/test_complete_daily_session.py`): `test_snapshot_has_daily_reason_and_session_id`, `test_second_complete_is_a_noop` (rows and re-check stage unchanged, `already_completed=True`), `test_checked_mastered_key_advances_recheck`, `test_unfinished_job_refuses`, `test_non_daily_session_refuses`. Plus `test_rebuild_profile_accepts_reason_and_session` in `tests/app/test_rebuild_profile.py`.

- [ ] **Step 2: Run to verify they fail, implement, run to pass.** Run: `uv run pytest tests/app/test_complete_daily_session.py tests/app/test_rebuild_profile.py -q`. Expected: FAIL first, then PASS after implementing `complete_daily_session` and the `rebuild_profile` parameters.

- [ ] **Step 3: Write failing API and CLI tests** (`tests/api/test_complete_api.py`: 200, idempotent second call, 409 while a job is queued; `tests/test_cli.py`: `test_daily_complete_prints_confirmation`).

- [ ] **Step 4: Implement the route and CLI commands, run to pass.** Run: `uv run pytest tests/api/test_complete_api.py tests/test_cli.py -q`. Expected: PASS.

- [ ] **Step 5: Write the end-to-end test** `tests/e2e/test_daily_loop.py::test_full_daily_loop_through_api` using `TestClient`, a seeded post-baseline profile (via `dev/seed.py` observations rebuilt into the profile), a seeded prompt bank in `content_items`, the fakes above, and a mutable test clock:
  1. `POST /api/plan/today` → 201; foci include one key per skill.
  2. `POST /api/plan/today/session` → attempt id.
  3. `POST /api/attempts/{id}/recording` with the synthetic WAV → 202, job id; run the queued job; `GET /api/jobs/{id}` is `done`.
  4. `POST /api/sessions/{id}/feedback` → three `fix` cards, `degraded=False`, every `error_key` in the taxonomy and equal to a key the fakes made miss.
  5. `POST /api/sessions/{id}/complete` → 200; `profile_snapshots` has a `daily` snapshot for the session.
  6. Advance the clock one UTC day; `POST /api/plan/today` → the plan's focus for the skill of today's worst miss equals that key (seed the fakes so it dominates), proving tomorrow's plan reflects today's misses.
  - Variants in the same file: `test_loop_with_capped_coach_still_gives_template_feedback_and_a_plan` (`FakeCoach` raising `CapExceeded`: cards are `source='template'` with reason `cap_exceeded`, completion and tomorrow's plan still work); `test_loop_without_pronunciation_scorer_marks_sounds_not_scored` (scorer fake raising `CapabilityMissing`: sounds card is `not_scored`, the other two still have fixes); `test_feedback_before_job_run_is_409`.

- [ ] **Step 6: Write the CLI end-to-end test** `tests/e2e/test_daily_loop_cli.py::test_daily_run_through_cli`: the same fakes and app, `cli.main(["daily", "run", str(wav)], client=ApiClient(TestClient(app)))` returns 0 and prints three cards; running `["plan"]` the next UTC day prints the focus key of today's worst miss.

- [ ] **Step 7: Run to verify the e2e tests fail, then fix wiring until they pass.** Run: `uv run pytest tests/e2e -q`. Expected: FAIL first (missing wiring), then PASS. Any missing seam in 0c–0e that cannot be bridged by an adapter in `api/deps.py` goes into HANDOFF as a blocker rather than being patched in their modules.

- [ ] **Step 8: Regenerate the contract and run everything.** Run: `make gen-api && make test && make lint`. Expected: green.

- [ ] **Step 9: Deliver** (branch `p1/10-complete-session-e2e`).

---

### Task 11: Phase 1 verification, security review and handoff

**Branch:** `p1/11-phase-verification`

**Files:**
- Modify: `docs/superpowers/HANDOFF.md`, `docs/ARCHITECTURE.md` (record the Phase 1 additions to §7: `feedback_items.source`, `feedback_items.fallback_reason`, `profile_entries.recheck_stage`; the `POST` plan and feedback endpoints; `nosolear plan` and `nosolear daily` commands; mark Phase 1 done)

- [ ] **Step 1: Whole-phase gate.** Run from the repo root: `make test && make lint`, then `cd apps/api && HYPOTHESIS_PROFILE=heavy uv run pytest tests/domain -q`. Expected: all green.

- [ ] **Step 2: Confirm the contract is current.** Run: `make gen-api && git status --short`. Expected: no changes.

- [ ] **Step 3: List live tests, do not run them without keys.** Run: `cd apps/api && uv run pytest -m live --collect-only -q`. Expected: the Phase 1 live test `test_claude_explain_fixes_live` is listed. Record in HANDOFF that it is unverified against the live service and on which platform.

- [ ] **Step 4: Check the security properties by test.** Confirm these exist and pass: GET routes side-effect free (plan, feedback), hostile coach output rejected, planted key absent from feedback responses, logs and OpenAPI, and the composition-order test still passes with `Coach` used by `generate_feedback`.

- [ ] **Step 5: Run `/security-review`** on the phase's diff (`git diff origin/main...`) and fix every finding in a follow-up commit on this branch, test first.

- [ ] **Step 6: Update `HANDOFF.md` and `ARCHITECTURE.md`** as listed under Files; mark Phase 1 done with today's date; list adapters still unverified live; note the owner question about timezone-local days.

- [ ] **Step 7: Deliver** (branch `p1/11-phase-verification`).

---

## Self-review notes

- **Spec coverage (§13 Phase 1 and the referenced sections):** selection policy with Thompson sampling, variety, 2/4/8/16/32 re-checks, seed from the date (Tasks 1–2); daily plan with prompt, drills, steps and persistence in `daily_plans` (Tasks 3–4); plan endpoint and CLI (Task 5); recordings through the existing upload path (Task 6, 10); one-fix-per-skill chosen in the domain, coach explains only (Tasks 7–8); typed-error fallbacks to templates, never silent (Tasks 7–9); profile snapshot per daily session (Task 10); tomorrow's plan reflects today's misses (Task 10 e2e); `make gen-api` after each API change (Tasks 5, 6, 9, 10).
- **Decisions the spec left open:** day is the UTC date (§11); plan and feedback creation are `POST` because §15 forbids state-changing GETs; coach-written prompts deferred; focus never comes from keys the scoring config cannot score; a re-check counts as done when the session had an opportunity for the key.

## Cross-phase assumptions

- **0e:** `ProfileEntry.provisional: bool` (default `False`) on the domain dataclass and the repository round trip.
- **0e:** table `content_items` as in §7 with `target_keys` stored as JSON text; `attempts.content_item_id` nullable FK.
- **0e:** `ScoringConfigRepository.latest() -> ScoringConfig` and `ScoringConfig.scores_key(error_key: str) -> bool` (true when at least one detector is enabled for the key).
- **0e:** observation `evidence` carries `word`, `quote`, `start_ms`, `end_ms` where applicable.
- **0e:** extraction plus the 0c job's profile rebuild leave the profile current when the job is `done`.
- **0d:** `Coach.explain_fixes(fixes: Sequence[FixRequest]) -> Sequence[RawExplanation]` in `nosolear/ports/coach.py`, with `FixRequest(error_key, description, word, quote)` and `RawExplanation(error_key, message, model_text)`, and a structured-output schema whose `error_key` is the taxonomy enum; wrapped by cache → retry → metered in `api/deps.py`; a `FakeCoach` that records calls and can raise typed errors.
- **0c/0d:** `CapExceeded`, `ProviderUnavailable`, `CapabilityMissing` importable from `nosolear.domain.errors`.
- **0c:** `jobs(attempt_id, status)` as in §7; `POST /api/attempts/{id}/recording`; `GET /api/jobs/{id}`; a test hook to run queued jobs synchronously; `tests/audio.py` synthetic WAV factory.
- **0c:** CLI HTTP helper `nosolear.cli_client.ApiClient` (`get_json`, `post_json`, `upload_wav(attempt_id, path) -> job_id`, `follow_job(job_id) -> dict`) constructible from an `httpx.Client`, and `cli.main(argv, *, client=None)`.
- **0b:** `PRIVACY.md` exists with a per-provider "what is sent" table; `make test-live` and the `live` marker exist.

## Produces for later phases

- `select(...) -> Selection`, `Focus`, `RecheckProbe`, `seed_for_date(day) -> int` (`domain/selection.py`), and `RecheckState`, `advance_rechecks`, `RECHECK_DAYS` (`domain/rechecks.py`): Phase 3 drills and Phase 5 re-tests read foci and re-check state.
- `DailyPlan`, `PromptCandidate`, `DrillSpec`, `PlanStep`, `PLAN_STEPS`, `assemble_plan`, `choose_prompt` (`domain/daily_plan.py`); `build_daily_plan(...) -> StoredPlan` (`app/build_daily_plan.py`); tables `daily_plans`, `sessions.plan_id`, `profile_entries.next_recheck_at` and `recheck_stage`.
- HTTP: `POST /api/plan/today` (201/200), `GET /api/plan/today` (404 `no_plan_for_today`), `POST /api/plan/today/session`, `POST` and `GET /api/sessions/{id}/feedback`, `POST /api/sessions/{id}/complete`; generated TS types for them (Phase 2 screens).
- `FeedbackItem` / `feedback_items` rows with `source` and `fallback_reason`; `model_text` per card for Phase 2 to synthesize through the TTS cache.
- `generate_feedback`, `complete_daily_session`, `start_daily_session` use cases; CLI `nosolear plan`, `nosolear daily start|feedback|complete|run`.
- Phase 3 should replace `DrillSpec` stubs with real drill content and may call `choose_prompt` with a coach-extended bank.
