# Phase 0a: Foundation and Error-Profile Core: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the repository scaffold, CI and branch protection, plus the tested error-profile core. That core covers the taxonomy, observations, the Beta-with-forgetting estimator and status rules, SQLite persistence, a profile rebuild, and a profile API and page. With it in place, Phase 0c can plug real detectors into a working spine.

**Architecture:** A Python FastAPI backend (`apps/api`), organized as ports and adapters. The pure `domain` package holds every decision; `persistence` and `api` are adapters around it. A React + TypeScript SPA (`apps/web`) uses feature modules and generates its API types from the backend's OpenAPI schema. Nothing here calls Azure, Claude or a local model.

**Tech Stack:**
- Python 3.14, uv, FastAPI 0.162.4, SQLAlchemy 2.1.8, Alembic 1.20.1, SciPy 1.18.1, pytest 9.2.0, Hypothesis 6.170.15, ruff 0.17.4, pyright 1.1.414.
- Node 26, pnpm 12, React 19.3.1, Vite 8.3.8, TypeScript 5.9.3, TanStack Router 1.170.46, TanStack Query 5.107.1, openapi-fetch 0.17.0, openapi-typescript 7.13.0, Tailwind 4.3.5, Vitest 5.1.0, Testing Library 16.3.3, MSW 3.0.5, ESLint 10.14.0, typescript-eslint 8.72.2, eslint-plugin-boundaries 7.4.2.

**Spec:** [docs/ARCHITECTURE.md](../../ARCHITECTURE.md), mainly §3 (stack), §6 (error profile), §7 (data model) and §12 (testing and delivery).

## Global Constraints

- **Python:** `requires-python = ">=3.14,<3.15"`. All dependencies are pinned exactly (`==`) and locked by `uv.lock`.
- **TypeScript is pinned to 5.9.3,** because typescript-eslint supports `<6.1.0` and openapi-typescript requires `^5.x`. Revisit once both support TypeScript 7.
- **CI actions:**
  - `actions/checkout@v7`
  - `astral-sh/setup-uv@v10`
  - `pnpm/action-setup@v6`
  - `actions/setup-node@v7`
- **Context weights:** scripted `1.0`, unscripted `0.5`. An observation's weight is the context weight × detector confidence, with confidence in `(0, 1]`.
- **Priors:** `a0 = 1, b0 = 3` for hypothesis keys; `a0 = 1, b0 = 9` for all other keys.
- **Forgetting:** half-life `14` days, using `a ← a0 + (a − a0) · 2^(−days/H)`, and the same for `b`.
- **Interval:** central 80% Beta credible interval.
- **Status thresholds:**
  - `min_n` 5
  - `active_rate` 0.15
  - `improving_drop` 0.30
  - `improving_lookback_days` 14
  - `mastered_ci_high` 0.10
  - `mastered_min_n` 20
  - `relapse_rate` 0.20
- **Impact:** an integer from 1 to 3. Report priority = `p_hat × impact`.
- **Dependency rules:**
  - `domain` imports no I/O libraries: no SQLAlchemy, FastAPI or filesystem access.
  - Web `features/*` never import each other.
  - `shared/*` never imports `features/*`.
- **Repository hygiene:**
  - Never commit audio files (`.wav .webm .ogg .m4a .mp3 .flac`) or anything under `data/`.
  - Test fixtures never contain the user's voice.
  - CI never has API keys.
- **Delivery:**
  - Each task gets its own branch, named `p0a/NN-<slug>`, with test-first commits pushed as you go.
  - Open a PR, and squash-merge only once CI is green.
  - **No `Co-Authored-By` trailers and no "Generated with Claude Code" footers.**
- **Versions:** `TAXONOMY_VERSION = 1`, `ALGO_VERSION = 1`.

## Review Focus

These are the inputs most likely to bite that the spec implies but the obvious tests skip. Each has a test pinned in its owning task.

1. **Out-of-order or naive timestamps.** Detectors can deliver observations in any order, and a naive datetime silently shifts by the user's UTC offset (+05:45 in Nepal). Expect naive datetimes to be rejected, and shuffled input to produce an identical profile. Tested in Task 3 (`test_rejects_naive_datetime`, `test_converts_offset_to_utc`) and Task 4 (`test_build_profile_is_order_independent`).
2. **Typo or malformed error keys from detectors or the coach** (`grammar.artcle`, `sound.sub.v`, `sound.sub.v.v`). These must be rejected with `UnknownErrorKey`, never stored. Tested in Task 3 (`test_rejects_malformed_keys`).
3. **Fresh install with an empty database.** `GET /api/profile` must return 200 with empty entries, and the page must show an empty state, not an error. Tested in Task 7 (`test_profile_empty_db`) and Task 8 (`shows the empty state`).
4. **Bad detector confidence** (`0`, `1.2`, `NaN`, negative). It must raise `ValueError`, so NaN can never poison `a` or `b`. Tested in Task 3 (`test_rejects_bad_confidence`).
5. **`as_of` earlier than some observations** (a rebuild for a past date, or clock skew). Later observations must be excluded rather than applied "from the future". Tested in Task 4 (`test_excludes_observations_after_as_of`).

## Not in This Plan

These parts of the spec are deliberately left out:
- **Phase 0c (after the spikes):** recording, Azure/Claude/local-model adapters, the job runner, the usage ledger, the TTS cache, content items and XState flows.
- **Phase 1:** the Thompson-sampling selection policy (§6.6) and daily plans.

## File Map

```
Makefile                                   setup / api / web / test / lint / gen-api
.node-version                              26
.env.example                               documented env vars (no values)
.github/workflows/ci.yml                   jobs: hygiene, api, web, contract
scripts/check-no-personal-data.sh          reads paths on stdin; exits 1 on audio or data/
scripts/git-hooks/pre-commit               runs the check on staged files
apps/api/
  pyproject.toml, uv.lock, .python-version
  alembic.ini
  src/nosolear/
    settings.py                            Settings (env prefix NOSOLEAR_)
    cli.py                                 nosolear CLI (db upgrade, rebuild-profile, dev-seed)
    domain/taxonomy.py                     Skill, Family, Detector, KeyDefinition, Taxonomy, DEFAULT_TAXONOMY
    domain/observations.py                 Outcome, Context, Observation, make_observation
    domain/estimates.py                    Prior, BetaState, KeyEstimate, decay, apply, estimate (Beta math only)
    domain/status.py                       Status, StatusThresholds, classify
    domain/profile.py                      ProfileConfig, prior_for, ProfileEntry, Profile, build_profile
    ports/clock.py                         Clock protocol
    ports/stores.py                        ObservationReader, ProfileWriter protocols
    adapters/system_clock.py               SystemClock
    persistence/db.py                      create_engine_for, upgrade_to_head
    persistence/models.py                  SQLAlchemy tables, UTCDateTime
    persistence/repositories.py            ObservationRepository, ProfileRepository
    persistence/migrations/                Alembic env + versions/0001_initial.py
    app/rebuild_profile.py                 rebuild_profile use case
    dev/seed.py                            deterministic synthetic observations
    api/app.py                             create_app, lifespan, /api/health
    api/profile_routes.py, api/schemas.py  GET /api/profile
    api/export_openapi.py                  prints the OpenAPI JSON
  tests/                                   mirrors src/ (domain/, persistence/, app/, api/, scripts/)
apps/web/
  package.json, pnpm-lock.yaml, vite.config.ts, tsconfig.json, eslint.config.js
  src/main.tsx, src/index.css
  src/app/router.tsx, src/app/AppProviders.tsx
  src/features/home/HomePage.tsx
  src/features/progress/ProfilePage.tsx, useProfile.ts, formatRate.ts, statusLabel.ts
  src/shared/api/openapi.json (generated), schema.d.ts (generated), client.ts
  src/test/setup.ts, src/test/server.ts
```

---

### Task 1: API scaffold, repo hygiene, CI and branch protection

**Files:**
- Create:
  - `Makefile`, `.env.example`
  - `scripts/check-no-personal-data.sh`, `scripts/git-hooks/pre-commit`
  - `.github/workflows/ci.yml`
  - `apps/api/pyproject.toml`, `apps/api/.python-version` (`3.14`)
  - `apps/api/src/nosolear/__init__.py`, `apps/api/src/nosolear/settings.py`
  - `apps/api/src/nosolear/api/__init__.py`, `apps/api/src/nosolear/api/app.py`
- Test:
  - `apps/api/tests/api/test_health.py`
  - `apps/api/tests/scripts/test_check_no_personal_data.py`

**Interfaces:**
- **Produces:**
  - `Settings(BaseSettings)`, which reads env prefix `NOSOLEAR_` and the `.env` file at the repo root (`env_file = <repo root>/.env`, so it works from any directory):
    - `data_dir: Path`, defaulting to `<repo root>/data`. The root is resolved from `settings.py` as `Path(__file__).resolve().parents[4]`.
    - property `database_url -> str`, which returns `f"sqlite:///{data_dir / 'nosolear.sqlite'}"`.
  - `create_app(settings: Settings | None = None) -> FastAPI` in `nosolear/api/app.py`, with `GET /api/health -> HealthResponse(status: Literal["ok"])`.
  - CI job names `hygiene` and `api`. Branch protection requires them.

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/test_health.py
from fastapi.testclient import TestClient
from nosolear.api.app import create_app

def test_health_ok():
    r = TestClient(create_app()).get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

```python
# tests/scripts/test_check_no_personal_data.py
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check-no-personal-data.sh"

def run(paths: list[str]) -> int:
    return subprocess.run(["bash", str(SCRIPT)], input="\n".join(paths), text=True).returncode

def test_allows_code_and_docs():
    assert run(["apps/api/src/nosolear/settings.py", "docs/plan-sketch.png", "README.md"]) == 0

def test_blocks_audio_and_data_dir():
    for bad in ["data/nosolear.sqlite", "x/take.WAV", "a.webm", "b.m4a", "c.mp3", "d.ogg", "e.flac"]:
        assert run([bad]) == 1, bad
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `cd apps/api && uv run pytest -q`
Expected: FAIL (`ModuleNotFoundError: nosolear.api`, and a missing script).

- [ ] **Step 3: Implement**
  - **`pyproject.toml`:**
    - runtime deps: `fastapi==0.162.4`, `uvicorn==0.54.0`, `pydantic-settings==2.16.2`.
    - dev dependency group: `pytest==9.2.0`, `hypothesis==6.170.15`, `ruff==0.17.4`, `pyright==1.1.414`, `httpx==0.28.1`.
    - build backend: `uv_build`.
    - ruff: line length 100, rules `E,F,I,UP,B,SIM,RUF`.
    - pyright: `strict` for `src/`.
  - **`check-no-personal-data.sh`:**
    - reads newline-separated paths from stdin;
    - case-insensitively matches `\.(wav|webm|ogg|m4a|mp3|flac)$` or the prefix `data/`;
    - prints offenders and exits 1, otherwise exits 0.
  - **`pre-commit`:** runs `git diff --cached --name-only --diff-filter=ACM | scripts/check-no-personal-data.sh`.
  - **`Makefile` targets:**
    - `setup`: `uv sync` in `apps/api`, and `git config core.hooksPath scripts/git-hooks`.
    - `api`: `uv run uvicorn nosolear.api.app:create_app --factory --reload --port 8000`.
    - `test` and `lint`.
  - **`.env.example`:** lists `NOSOLEAR_DATA_DIR=` with a comment.
  - **`ci.yml`:** runs on `pull_request` and on `push` to `main`. Two jobs:
    - **`hygiene`:** `git ls-files | bash scripts/check-no-personal-data.sh`.
    - **`api`:** with `working-directory: apps/api`, run `uv sync --locked`, `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`, `uv run pytest -q`.

- [ ] **Step 4: Run the tests and lint, and confirm they pass**

Run: `make setup && cd apps/api && uv run pytest -q && uv run ruff check && uv run pyright`
Expected: 3 passed, and no lint or type errors.

- [ ] **Step 5: Commit, push and open the PR**

```bash
git switch -c p0a/01-api-scaffold
git add Makefile .env.example scripts .github apps/api
git commit -m "Scaffold API, hygiene checks and CI"
git push -u origin p0a/01-api-scaffold && gh pr create --fill
```

- [ ] **Step 6: Merge once CI is green, then protect `main`**

```bash
gh pr checks --watch && gh pr merge --squash --delete-branch
gh api -X PUT repos/shreyandhawa/nosolear/branches/main/protection --input - <<'JSON'
{"required_status_checks":{"strict":false,"contexts":["hygiene","api"]},
 "enforce_admins":true,
 "required_pull_request_reviews":{"required_approving_review_count":0},
 "restrictions":null}
JSON
```

Verify: `gh api repos/shreyandhawa/nosolear/branches/main/protection -q '.required_status_checks.contexts'` prints `["hygiene","api"]`.

---

### Task 2: Web scaffold with enforced module boundaries

**Files:**
- Create:
  - `.node-version` (`26`)
  - `apps/web/package.json`, `vite.config.ts`, `tsconfig.json`, `eslint.config.js`, `index.html`
  - `src/main.tsx`, `src/index.css`
  - `src/app/router.tsx`, `src/app/AppProviders.tsx`
  - `src/features/home/HomePage.tsx`
  - `src/test/setup.ts`
- Modify: `.github/workflows/ci.yml` (add the `web` job), `Makefile` (add `pnpm install` to `setup`, and a `web` target).
- Test: `src/features/home/HomePage.test.tsx`, `src/app/boundaries.test.ts`

**Interfaces:**
- **Produces:**
  - `createAppRouter(): Router`, which uses code-based TanStack Router routes. Route `/` renders `HomePage`.
  - `AppProviders({ children })`, which wraps a `QueryClientProvider`.
  - `src/index.css` contains `@import "tailwindcss";`.
  - CI job name `web`.

- [ ] **Step 1: Write the failing tests**

```tsx
// src/features/home/HomePage.test.tsx
import { render, screen } from "@testing-library/react";
import { HomePage } from "./HomePage";

test("shows the app name and tagline", () => {
  render(<HomePage />);
  expect(screen.getByRole("heading", { name: "Nosolear" })).toBeInTheDocument();
  expect(screen.getByText("Speak daily, get scored, drill your own weak spots.")).toBeInTheDocument();
});
```

```ts
// src/app/boundaries.test.ts
import { ESLint } from "eslint";

test("a feature importing another feature is a lint error", async () => {
  const eslint = new ESLint();
  const [result] = await eslint.lintText(
    'import { HomePage } from "../home/HomePage";\nexport const x = HomePage;\n',
    { filePath: "src/features/other/Bad.ts" },
  );
  expect(result.messages.some((m) => m.ruleId?.startsWith("boundaries/"))).toBe(true);
});

test("shared importing a feature is a lint error", async () => {
  const eslint = new ESLint();
  const [result] = await eslint.lintText(
    'import { HomePage } from "../../features/home/HomePage";\nexport const y = HomePage;\n',
    { filePath: "src/shared/lib/bad.ts" },
  );
  expect(result.messages.some((m) => m.ruleId?.startsWith("boundaries/"))).toBe(true);
});
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `cd apps/web && pnpm test --run`
Expected: FAIL (`HomePage` doesn't exist yet, and no boundaries rules are configured).

- [ ] **Step 3: Implement**
  - **Dependencies:** pin exact versions from the Tech Stack line, plus `@vitejs/plugin-react 6.3.0`, `jsdom 31.0.0` and `eslint-import-resolver-typescript 4.4.5`. Set the resolver in ESLint `settings` so boundaries can resolve `.tsx` imports.
  - **Vitest:** environment `jsdom`, with `setupFiles: ["src/test/setup.ts"]`, which imports `@testing-library/jest-dom/vitest`.
  - **ESLint flat config:** `typescript-eslint` recommended rules, plus `eslint-plugin-boundaries` with these element types:
    - `app`: `src/app/**`
    - `feature`: `src/features/*`, captured by folder name
    - `shared`: `src/shared/**`
  - **Allowed imports:** `app → feature, shared`; `feature → shared` and its own folder; `shared → shared`.
  - **Scripts:** `dev`, `build`, `lint`, `typecheck` (`tsc --noEmit`), `test`.
  - **CI job `web`:** in `apps/web`, run `pnpm install --frozen-lockfile`, `pnpm lint`, `pnpm typecheck`, `pnpm test --run`, `pnpm build`.

- [ ] **Step 4: Run all checks and confirm they pass**

Run: `cd apps/web && pnpm lint && pnpm typecheck && pnpm test --run && pnpm build`
Expected: 3 tests pass and the build succeeds.

- [ ] **Step 5: Commit, open the PR, merge when green, and add `web` to the required checks**

```bash
git switch -c p0a/02-web-scaffold && git add .node-version apps/web .github Makefile
git commit -m "Scaffold web app with enforced module boundaries"
git push -u origin p0a/02-web-scaffold && gh pr create --fill
gh pr checks --watch && gh pr merge --squash --delete-branch
gh api -X PATCH repos/shreyandhawa/nosolear/branches/main/protection/required_status_checks \
  -f 'contexts[]=hygiene' -f 'contexts[]=api' -f 'contexts[]=web'
```

---

### Task 3: Taxonomy and observations

**Files:**
- Create: `apps/api/src/nosolear/domain/__init__.py`, `taxonomy.py`, `observations.py`
- Test: `apps/api/tests/domain/test_taxonomy.py`, `test_observations.py`

**Interfaces:**
- **Produces, in `domain/taxonomy.py`:**
  - `class Skill(StrEnum)`: `SOUNDS="sounds"`, `ON_THE_SPOT="on_the_spot"`, `ARTICULATE="articulate"`.
  - `class Family(StrEnum)`: `SUB="sound.sub"`, `LOW="sound.low"`, `INS="sound.ins"`, `DEL="sound.del"`, `PROSODY="prosody"`, `FLUENCY="fluency"`, `GRAMMAR="grammar"`, `STRUCTURE="structure"`, `CLARITY="clarity"`.
  - `class Detector(StrEnum)`: `AZURE_PA="azure_pa"`, `PHONE_PROBE="phone_probe"`, `ASR_METRICS="asr_metrics"`, `COACH="coach"`.
  - `@dataclass(frozen=True, slots=True) class KeyDefinition`, with fields `key: str`, `family: Family`, `skill: Skill`, `impact: int`, `drill_family: str`, `detectors: frozenset[Detector]`, `hypothesis: bool`, `description: str`.
  - `class UnknownErrorKey(ValueError)`.
  - `class Taxonomy` with:
    - `__init__(definitions, version: int)`
    - `.version`
    - `.get(key) -> KeyDefinition`
    - `__contains__`
    - `.defined() -> tuple[KeyDefinition, ...]`, sorted by key.
  - `TAXONOMY_VERSION = 1` and `DEFAULT_TAXONOMY`.
- **Produces, in `domain/observations.py`:**
  - `class Outcome(StrEnum)`: `MISS`, `OK`.
  - `class Context(StrEnum)`: `SCRIPTED`, `UNSCRIPTED`.
  - `CONTEXT_WEIGHT: Mapping[Context, float]`.
  - `class DetectorNotAllowed(ValueError)`.
  - `@dataclass(frozen=True, slots=True) class Observation`, with fields `error_key`, `outcome`, `weight: float`, `detector`, `context`, `observed_at: datetime` (aware UTC), `taxonomy_version: int`, `attempt_id: str | None`, `evidence: Mapping[str, object]`.
  - `make_observation(*, taxonomy, error_key, outcome, detector, context, observed_at, confidence=1.0, attempt_id=None, evidence=None) -> Observation`.

**Family → skill:** `SUB`, `LOW`, `INS`, `DEL` and `PROSODY` → `SOUNDS`; `FLUENCY` and `GRAMMAR` → `ON_THE_SPOT`; `STRUCTURE` and `CLARITY` → `ARTICULATE`.

**Explicit keys.** Phone symbols follow Azure's en-US IPA set; spike S1 verifies the symbols, and any change to them is a taxonomy version bump. Write a short plain-English `description` for each key.

| Key | Impact | Drill family | Detectors | Hypothesis |
|---|---|---|---|---|
| `sound.sub.v.w`, `sound.sub.w.v`, `sound.sub.f.p`, `sound.sub.ʃ.s`, `sound.sub.s.ʃ` | 3 | `minimal_pairs` | azure_pa, phone_probe | yes |
| `sound.sub.θ.t`, `sound.sub.z.dʒ`, `sound.sub.z.s` | 2 | `minimal_pairs` | azure_pa, phone_probe | yes |
| `sound.sub.ð.d`, `sound.sub.ʒ.dʒ` | 1 | `minimal_pairs` | azure_pa, phone_probe | yes |
| `sound.sub.i.ɪ`, `sound.sub.ɪ.i`, `sound.sub.æ.ɛ` | 3 | `minimal_pairs` | azure_pa, phone_probe | yes |
| `sound.sub.ʌ.ɑ` | 2 | `minimal_pairs` | azure_pa, phone_probe | yes |
| `sound.low.t`, `sound.low.d`, `sound.low.ɹ`, `sound.low.ɝ` | 2 | `sound_practice` | azure_pa | yes |
| `sound.low.θ`, `sound.low.ð` | 1 | `sound_practice` | azure_pa | yes |
| `sound.ins.epenthesis_sC` | 2 | `cluster_practice` | phone_probe | yes |
| `sound.del.final_cluster` | 2 | `cluster_practice` | phone_probe, azure_pa | no |
| `prosody.word_stress` | 3 | `stress_practice` | *(none until Phase 2)* | yes |
| `prosody.unexpected_break`, `prosody.monotone` | 2 | `rhythm_practice` | azure_pa | yes |
| `prosody.missing_break` | 1 | `rhythm_practice` | azure_pa | no |
| `fluency.slow_start` | 3 | `rapid_questions` | asr_metrics | no |
| `fluency.filler`, `fluency.long_pause` | 2 | `rapid_questions` | asr_metrics | no |
| `fluency.false_start` | 1 | `rapid_questions` | asr_metrics | no |
| `grammar.verb_tense` | 3 | `grammar_rewrite` | coach | no |
| `grammar.article`, `grammar.preposition` | 2 | `grammar_rewrite` | coach | yes |
| `grammar.agreement` | 2 | `grammar_rewrite` | coach | no |
| `grammar.plural` | 1 | `grammar_rewrite` | coach | no |
| `structure.missing_point`, `structure.buried_point` | 3 | `pre_builder` | coach | no |
| `structure.missing_reason`, `structure.missing_example` | 2 | `pre_builder` | coach | no |
| `clarity.run_on`, `clarity.vague`, `clarity.wordy` | 2 | `clarity_rewrite` | coach | no |
| `clarity.repetition` | 1 | `clarity_rewrite` | coach | no |

**Dynamic keys.** Any substitution or weak-sound key not listed above is generated with defaults instead of being rejected:
- **Format:** `sound.sub.<expected>.<produced>` or `sound.low.<phone>`. Each phone part must be non-empty, contain no `.` or whitespace, and for substitutions, `expected != produced`.
- **Generated values:** impact 1, `hypothesis=False`.
  - `sub` keys: detectors `{azure_pa, phone_probe}`, drill family `minimal_pairs`, description `"/{e}/ said as /{p}/"`.
  - `low` keys: detectors `{azure_pa}`, drill family `sound_practice`, description `"/{p}/ unclear"`.
- **All other families:** only the explicit keys are valid.

**`make_observation` validation**, applied in this order:
1. The key must be in the taxonomy, else `UnknownErrorKey`.
2. The detector must be in `definition.detectors`, else `DetectorNotAllowed`.
3. Confidence must be finite and in `(0, 1]`, else `ValueError`.
4. `observed_at` must be timezone-aware, else `ValueError`. It is then converted to UTC.

Weight = `CONTEXT_WEIGHT[context] * confidence`. Evidence is stored as a copied `dict`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/domain/test_taxonomy.py
import pytest
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY as T, Detector, Family, Skill, UnknownErrorKey

HYPOTHESES = ["sound.sub.v.w", "sound.sub.w.v", "sound.sub.f.p", "sound.sub.θ.t", "sound.sub.ð.d",
              "sound.sub.ʃ.s", "sound.sub.s.ʃ", "sound.sub.z.dʒ", "sound.ins.epenthesis_sC",
              "prosody.word_stress", "grammar.article"]

def test_hypothesis_keys_present():
    assert all(T.get(k).hypothesis for k in HYPOTHESES)

def test_dynamic_substitution_key():
    d = T.get("sound.sub.p.b")
    assert (d.family, d.skill, d.impact, d.hypothesis) == (Family.SUB, Skill.SOUNDS, 1, False)
    assert d.detectors == frozenset({Detector.AZURE_PA, Detector.PHONE_PROBE})

@pytest.mark.parametrize("bad", ["", "fluency", "grammar.artcle", "sound.sub.v", "sound.sub.v.v",
                                 "sound.sub..w", "sound.sub.v.w.x", "sound.low.", "sound.sub.v. w"])
def test_rejects_malformed_keys(bad):
    with pytest.raises(UnknownErrorKey):
        T.get(bad)

def test_family_matches_skill_and_impact_range():
    sounds = {Family.SUB, Family.LOW, Family.INS, Family.DEL, Family.PROSODY}
    for d in T.defined():
        assert 1 <= d.impact <= 3
        assert (d.skill is Skill.SOUNDS) == (d.family in sounds)

def test_word_stress_not_scored_until_phase_2():
    assert T.get("prosody.word_stress").detectors == frozenset()
```

```python
# tests/domain/test_observations.py
import math
from datetime import datetime, timedelta, timezone
import pytest
from nosolear.domain.observations import Context, DetectorNotAllowed, Outcome, make_observation
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY as T, Detector

NPT = timezone(timedelta(hours=5, minutes=45))
T0 = datetime(2026, 11, 12, 8, 0, tzinfo=timezone.utc)

def obs(**kw):
    base = dict(taxonomy=T, error_key="sound.sub.v.w", outcome=Outcome.MISS,
                detector=Detector.AZURE_PA, context=Context.SCRIPTED, observed_at=T0)
    return make_observation(**(base | kw))

def test_weights():
    assert obs().weight == 1.0
    assert obs(context=Context.UNSCRIPTED, confidence=0.8).weight == pytest.approx(0.4)

def test_rejects_naive_datetime():
    with pytest.raises(ValueError):
        obs(observed_at=datetime(2026, 11, 12, 8, 0))

def test_converts_offset_to_utc():
    o = obs(observed_at=datetime(2026, 11, 12, 13, 45, tzinfo=NPT))
    assert o.observed_at == T0 and o.observed_at.tzinfo == timezone.utc

@pytest.mark.parametrize("c", [0.0, -0.1, 1.2, math.nan, math.inf])
def test_rejects_bad_confidence(c):
    with pytest.raises(ValueError):
        obs(confidence=c)

def test_rejects_detector_not_allowed():
    with pytest.raises(DetectorNotAllowed):
        obs(error_key="sound.ins.epenthesis_sC", detector=Detector.AZURE_PA)
    with pytest.raises(DetectorNotAllowed):
        obs(error_key="prosody.word_stress", detector=Detector.AZURE_PA)

def test_records_taxonomy_version_and_copies_evidence():
    ev = {"word": "vest"}
    o = obs(evidence=ev)
    ev["word"] = "changed"
    assert o.evidence == {"word": "vest"} and o.taxonomy_version == 1
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `cd apps/api && uv run pytest tests/domain -q`
Expected: FAIL (`ModuleNotFoundError: nosolear.domain`).

- [ ] **Step 3: Implement `domain/taxonomy.py` and `domain/observations.py`** to the interfaces and table above.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/domain -q && uv run pyright`
Expected: all pass, with 0 pyright errors.

- [ ] **Step 5: Commit, open the PR, and merge when green**

```bash
git switch -c p0a/03-taxonomy-observations
git add apps/api/src/nosolear/domain apps/api/tests/domain
git commit -m "Add error taxonomy and validated observations"
git push -u origin HEAD && gh pr create --fill && gh pr checks --watch && gh pr merge --squash --delete-branch
```

---

### Task 4: Profile estimator and status rules

**Files:**
- Create: `apps/api/src/nosolear/domain/estimates.py`, `apps/api/src/nosolear/domain/status.py`, `apps/api/src/nosolear/domain/profile.py`. Imports run one way only: `estimates ← status ← profile`.
- Modify: `apps/api/pyproject.toml` (add `scipy==1.18.1`)
- Test:
  - `apps/api/tests/domain/test_status.py`
  - `apps/api/tests/domain/test_profile.py`
  - `apps/api/tests/domain/test_profile_properties.py`

**Interfaces:**
- **Consumes:** `Observation`, `Taxonomy`, and `KeyDefinition` from Task 3.
- **Produces, in `domain/status.py`:**
  - `class Status(StrEnum)`: `UNKNOWN="unknown"`, `ACTIVE="active"`, `IMPROVING="improving"`, `WATCHING="watching"`, `MASTERED="mastered"`.
  - `@dataclass(frozen=True, slots=True) class StatusThresholds`, defaulting to the Global Constraints values.
  - `classify(est: KeyEstimate, *, previous: Status | None, p_hat_lookback: float | None, t: StatusThresholds) -> Status`.
- **Produces, in `domain/estimates.py`:**
  - `Prior(a0: float, b0: float)`, with `HYPOTHESIS_PRIOR = Prior(1, 3)` and `DEFAULT_PRIOR = Prior(1, 9)`.
  - `BetaState(a: float, b: float, updated_at: datetime)`.
  - `decay(state, *, to: datetime, prior: Prior, half_life_days: float) -> BetaState`.
  - `apply(state, obs: Observation) -> BetaState`. Raises `ValueError` if `obs.observed_at < state.updated_at`.
  - `KeyEstimate(p_hat, ci_low, ci_high, n_eff)` and `estimate(state, *, prior, level) -> KeyEstimate`. The interval uses `scipy.stats.beta.ppf((1 ± level) / 2, a, b)`.
- **Produces, in `domain/profile.py`:**
  - `prior_for(defn) -> Prior`, which returns `HYPOTHESIS_PRIOR` if `defn.hypothesis`, otherwise `DEFAULT_PRIOR`.
  - `ProfileConfig(half_life_days=14.0, interval_level=0.8, thresholds=StatusThresholds())`.
  - `ProfileEntry(definition, state, estimate, status, last_seen_at, priority)`.
  - `Profile(as_of, taxonomy_version, algo_version, entries: tuple[ProfileEntry, ...])`.
  - `ALGO_VERSION = 1`.
  - `build_profile(observations, *, as_of, taxonomy, config=ProfileConfig()) -> Profile`.

**`classify` rules, checked in order:**
1. `n_eff < min_n` → `UNKNOWN`.
2. `previous is MASTERED` → `ACTIVE` if `p_hat > relapse_rate`, otherwise `MASTERED`.
3. `ci_high < mastered_ci_high and n_eff >= mastered_min_n` → `MASTERED`.
4. `p_hat >= active_rate` → `IMPROVING` if `p_hat_lookback is not None and p_hat <= (1 - improving_drop) * p_hat_lookback`, otherwise `ACTIVE`.
5. Anything else → `WATCHING`.

**`build_profile` algorithm:**
1. Drop observations with `observed_at > as_of`.
2. Sort the rest by `(observed_at, error_key, outcome)`.
3. For each key, start from `BetaState(prior.a0, prior.b0, first observed_at)`.
4. For each observation, `decay` to its `observed_at`, then `apply` it.
5. After the last observation at each distinct `observed_at` for a key (an attempt's observations share one timestamp), compute the estimate:
   - append `(observed_at, p_hat)` to that key's history;
   - re-classify, with `previous` set to the key's last status and `p_hat_lookback` set to the newest history `p_hat` at or before `observed_at − 14 days`.
6. Finally, decay every key to `as_of`, then:
   - estimate and classify once more, with the lookback measured from `as_of`;
   - set `priority = p_hat * impact`.
7. Include only keys with at least one observation. Sort entries by priority descending, then key ascending.

`n_eff = a + b − a0 − b0`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/domain/test_status.py
from nosolear.domain.estimates import KeyEstimate
from nosolear.domain.status import Status, StatusThresholds, classify

T = StatusThresholds()
def est(p, hi=0.5, n=10.0): return KeyEstimate(p_hat=p, ci_low=0.0, ci_high=hi, n_eff=n)

def test_rules():
    assert classify(est(0.3, n=4), previous=None, p_hat_lookback=None, t=T) is Status.UNKNOWN
    assert classify(est(0.20), previous=None, p_hat_lookback=None, t=T) is Status.ACTIVE
    assert classify(est(0.20), previous=Status.ACTIVE, p_hat_lookback=0.30, t=T) is Status.IMPROVING
    assert classify(est(0.22), previous=Status.ACTIVE, p_hat_lookback=0.30, t=T) is Status.ACTIVE
    assert classify(est(0.05, hi=0.08, n=25), previous=None, p_hat_lookback=None, t=T) is Status.MASTERED
    assert classify(est(0.05, hi=0.12, n=25), previous=None, p_hat_lookback=None, t=T) is Status.WATCHING
    assert classify(est(0.18), previous=Status.MASTERED, p_hat_lookback=None, t=T) is Status.MASTERED
    assert classify(est(0.21), previous=Status.MASTERED, p_hat_lookback=None, t=T) is Status.ACTIVE
```

```python
# tests/domain/test_profile.py  (helper `mk(key, outcome, at, context=SCRIPTED, detector=AZURE_PA)` wraps make_observation)
from datetime import timedelta
import pytest
# T0 = 2026-11-12T08:00Z; DAY = timedelta(days=1)

def test_counts_without_decay():
    obs = [mk("sound.sub.v.w", MISS, T0)] * 10 + [mk("sound.sub.v.w", OK, T0)] * 30
    e = build_profile(obs, as_of=T0, taxonomy=TAX).entries[0]
    assert (e.state.a, e.state.b) == (11, 33)
    assert e.estimate.p_hat == pytest.approx(0.25) and e.estimate.n_eff == pytest.approx(40)
    assert e.estimate.ci_low < 0.25 < e.estimate.ci_high and e.status is Status.ACTIVE

def test_half_life_decay():
    obs = [mk("sound.sub.v.w", MISS, T0)] * 10 + [mk("sound.sub.v.w", OK, T0)] * 30
    e = build_profile(obs, as_of=T0 + 14 * DAY, taxonomy=TAX).entries[0]
    assert (e.state.a, e.state.b) == (pytest.approx(6), pytest.approx(18))

def test_unscripted_counts_half():
    e = build_profile([mk("sound.sub.v.w", MISS, T0, context=UNSCRIPTED)], as_of=T0, taxonomy=TAX).entries[0]
    assert (e.state.a, e.state.b) == (1.5, 3)

def test_non_hypothesis_prior():
    e = build_profile([mk("sound.sub.p.b", OK, T0)], as_of=T0, taxonomy=TAX).entries[0]
    assert e.estimate.p_hat == pytest.approx(1 / 11)

def test_sorted_by_priority():
    vw = [mk("sound.sub.v.w", MISS, T0)] * 10 + [mk("sound.sub.v.w", OK, T0)] * 30   # 0.25 × 3 = 0.75
    tt = [mk("sound.sub.θ.t", MISS, T0)] * 3 + [mk("sound.sub.θ.t", OK, T0)]          # 0.50 × 2 = 1.00
    keys = [e.definition.key for e in build_profile(vw + tt, as_of=T0, taxonomy=TAX).entries]
    assert keys == ["sound.sub.θ.t", "sound.sub.v.w"]

def test_excludes_observations_after_as_of():
    p = build_profile([mk("sound.sub.v.w", MISS, T0 + DAY)], as_of=T0, taxonomy=TAX)
    assert p.entries == ()

def test_improving_after_two_weeks_of_better_results():
    early = [mk("sound.sub.v.w", MISS, T0)] * 6 + [mk("sound.sub.v.w", OK, T0)] * 4    # ~0.5
    late = [mk("sound.sub.v.w", MISS, T0 + 15 * DAY)] * 3 + [mk("sound.sub.v.w", OK, T0 + 15 * DAY)] * 17
    e = build_profile(early + late, as_of=T0 + 15 * DAY, taxonomy=TAX).entries[0]
    assert e.status is Status.IMPROVING
```

```python
# tests/domain/test_profile_properties.py  (Hypothesis strategies: outcomes, contexts, offsets in [0, 60] days)
@given(state=beta_states(), at_offset=offsets())
def test_miss_never_lowers_and_ok_never_raises_p_hat(state, at_offset): ...
    # p_hat after apply(MISS) >= before; after apply(OK) <= before

@given(state=beta_states(), d1=offsets(), d2=offsets())
def test_decay_stays_above_prior_and_n_eff_never_grows(state, d1, d2): ...
    # a >= a0, b >= b0; n_eff(decay to t+max) <= n_eff(decay to t+min); decaying a prior-only state is identity

@given(obs_list=observation_lists())
def test_estimates_are_finite_and_ordered(obs_list): ...
    # 0 < p_hat < 1; 0 <= ci_low <= ci_high <= 1; all values finite

@given(obs_list=observation_lists(), seed=st.randoms())
def test_build_profile_is_order_independent(obs_list, seed): ...
    # build_profile(shuffled) == build_profile(original)
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `uv run pytest tests/domain -q`
Expected: FAIL (`ModuleNotFoundError: nosolear.domain.estimates`).

- [ ] **Step 3: Implement `estimates.py`, `status.py` and `profile.py`** to the interfaces and algorithm above. Add `scipy==1.18.1`.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/domain -q && uv run pyright`
Expected: all pass, with Hypothesis reporting no falsifying examples.

- [ ] **Step 5: Commit, open the PR, and merge when green**

```bash
git switch -c p0a/04-profile-estimator
git add apps/api
git commit -m "Add Beta-with-forgetting profile estimator and status rules"
git push -u origin HEAD && gh pr create --fill && gh pr checks --watch && gh pr merge --squash --delete-branch
```

---

### Task 5: SQLite persistence and repositories

**Files:**
- Create:
  - `apps/api/alembic.ini`
  - `apps/api/src/nosolear/persistence/__init__.py`, `db.py`, `models.py`, `repositories.py`
  - `apps/api/src/nosolear/persistence/migrations/env.py`, `script.py.mako`, `versions/0001_initial.py`
  - `apps/api/src/nosolear/ports/__init__.py`, `ports/stores.py`
- Modify: `apps/api/pyproject.toml` (add `sqlalchemy==2.1.8`, `alembic==1.20.1`)
- Test: `apps/api/tests/conftest.py`, `apps/api/tests/persistence/test_db.py`, `test_repositories.py`

**Interfaces:**
- **Consumes:** `Observation` (Task 3); `Profile`, `ProfileEntry` and `build_profile` (Task 4).
- **Produces:**
  - **`db.py`:**
    - `create_engine_for(url: str) -> Engine` creates the parent directory for file URLs, and sets `PRAGMA foreign_keys=ON` and `journal_mode=WAL` on every connection.
    - `upgrade_to_head(engine) -> None` runs Alembic programmatically.
  - **`models.py`:** `UTCDateTime(TypeDecorator)`. It stores ISO-8601 text with `+00:00`, returns aware UTC datetimes, and raises on naive input. Tables, per spec §7:
    - `sessions(id TEXT PK, kind, protocol_version, started_at, completed_at NULL)`, with `kind` constrained by CHECK to `baseline/daily/retest/conversation`.
    - `attempts(id TEXT PK, session_id FK, step, reference_text NULL, scripted BOOL, created_at)`.
    - `observations(id INTEGER PK, attempt_id FK NULL, error_key, outcome, weight, detector, context, observed_at, evidence_json, taxonomy_version, created_at)`, with `CHECK (weight > 0 AND weight <= 1)`.
    - `profile_entries(error_key PK, a, b, updated_at, p_hat, ci_low, ci_high, n_eff, status, last_seen_at, priority, as_of, algo_version, taxonomy_version)`.
    - `profile_snapshots(id TEXT PK, session_id FK NULL, reason, taken_at, as_of, algo_version, taxonomy_version, entries_json)`, with `reason` constrained by CHECK to `rebuild/baseline/daily/retest`.
  - **`ports/stores.py`:**
    - `ObservationReader(Protocol)`: `all() -> list[Observation]`.
    - `ProfileWriter(Protocol)`: `save(profile, *, session_id: str | None, reason: str) -> str`.
  - **`repositories.py`:**
    - `ObservationRepository(engine)`:
      - `add_many(observations: Sequence[Observation]) -> None`
      - `all() -> list[Observation]`, ordered by `observed_at, id`.
    - `ProfileRepository(engine, taxonomy)`:
      - `save(profile, *, session_id, reason) -> str` replaces every `profile_entries` row and appends a snapshot. Returns the snapshot id, a `uuid4().hex`.
      - `latest() -> Profile | None` rebuilds `Profile` from `profile_entries`, getting each `KeyDefinition` via `taxonomy.get`.
- **Test fixture:** `db_engine` in `conftest.py` creates `tmp_path/"db"/"t.sqlite"` and runs `upgrade_to_head`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/persistence/test_db.py
def test_creates_data_dir_and_migrates(tmp_path):
    eng = create_engine_for(f"sqlite:///{tmp_path}/nested/dir/x.sqlite")
    upgrade_to_head(eng)
    assert {"sessions", "attempts", "observations", "profile_entries",
            "profile_snapshots", "alembic_version"} <= set(inspect(eng).get_table_names())

def test_foreign_keys_enforced(db_engine):
    with pytest.raises(IntegrityError):
        ObservationRepository(db_engine).add_many([replace(OBS, attempt_id="missing")])
```

```python
# tests/persistence/test_repositories.py
def test_observation_roundtrip_keeps_utc_and_evidence(db_engine):
    o = mk("sound.sub.v.w", MISS, datetime(2026, 11, 12, 13, 45, tzinfo=NPT), evidence={"word": "vest", "start_ms": 120})
    repo = ObservationRepository(db_engine); repo.add_many([o])
    assert repo.all() == [o]

def test_profile_save_and_latest_roundtrip(db_engine):
    p = build_profile(SAMPLE_OBS, as_of=T0, taxonomy=TAX)
    repo = ProfileRepository(db_engine, TAX); repo.save(p, session_id=None, reason="rebuild")
    assert repo.latest() == p

def test_save_replaces_entries_and_appends_snapshot(db_engine):
    repo = ProfileRepository(db_engine, TAX)
    repo.save(build_profile(SAMPLE_OBS, as_of=T0, taxonomy=TAX), session_id=None, reason="rebuild")
    p2 = build_profile(SAMPLE_OBS[:1], as_of=T0, taxonomy=TAX)
    repo.save(p2, session_id=None, reason="rebuild")
    assert repo.latest() == p2 and count(db_engine, "profile_snapshots") == 2

def test_latest_is_none_on_empty_db(db_engine):
    assert ProfileRepository(db_engine, TAX).latest() is None
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `uv run pytest tests/persistence -q`
Expected: FAIL (`ModuleNotFoundError: nosolear.persistence`).

- [ ] **Step 3: Implement the persistence package and the `0001_initial` migration** to the interfaces above.

- [ ] **Step 4: Run all API tests and confirm they pass**

Run: `uv run pytest -q && uv run pyright`
Expected: all pass.

- [ ] **Step 5: Commit, open the PR, and merge when green**

```bash
git switch -c p0a/05-persistence
git add apps/api
git commit -m "Add SQLite persistence for observations and profiles"
git push -u origin HEAD && gh pr create --fill && gh pr checks --watch && gh pr merge --squash --delete-branch
```

---

### Task 6: Rebuild-profile use case and CLI

**Files:**
- Create:
  - `apps/api/src/nosolear/ports/clock.py`, `adapters/__init__.py`, `adapters/system_clock.py`
  - `apps/api/src/nosolear/app/__init__.py`, `app/rebuild_profile.py`
  - `apps/api/src/nosolear/dev/__init__.py`, `dev/seed.py`
  - `apps/api/src/nosolear/cli.py`
- Modify: `apps/api/pyproject.toml` (`[project.scripts] nosolear = "nosolear.cli:main"`), `Makefile` (add a `seed` target)
- Test: `apps/api/tests/app/test_rebuild_profile.py`, `apps/api/tests/test_cli.py`

**Interfaces:**
- **Consumes:** `ObservationReader`, `ProfileWriter`, `ObservationRepository`, `ProfileRepository` and `upgrade_to_head` (Task 5); `build_profile` (Task 4).
- **Produces:**
  - `Clock(Protocol)` with `now() -> datetime` (aware UTC); `SystemClock` implements it.
  - `rebuild_profile(*, observations: ObservationReader, profiles: ProfileWriter, taxonomy, clock, config=ProfileConfig()) -> Profile`. Saves with `reason="rebuild"` and `session_id=None`.
  - `seed_observations(*, days: int, seed: int, end: datetime) -> list[Observation]` returns deterministic synthetic data across these keys:
    - `sound.sub.v.w`, `sound.sub.f.p`, `sound.sub.θ.t`, `sound.ins.epenthesis_sC` (phone_probe)
    - `fluency.slow_start` (asr_metrics)
    - `grammar.article` (coach)
  - **CLI (`argparse`):**
    - `nosolear db upgrade`
    - `nosolear rebuild-profile` prints `Rebuilt profile: {n} keys as of {iso}`.
    - `nosolear dev-seed [--days 14] [--seed 7] [--force]` refuses with exit code 2 and the message `observations already exist; use --force` when the table isn't empty, unless `--force` is given. It runs `rebuild-profile` afterwards.

- [ ] **Step 1: Write the failing tests**

```python
# tests/app/test_rebuild_profile.py
def test_rebuild_uses_clock_and_saves_snapshot(db_engine):
    obs_repo = ObservationRepository(db_engine); obs_repo.add_many(SAMPLE_OBS)
    prof_repo = ProfileRepository(db_engine, TAX)
    p = rebuild_profile(observations=obs_repo, profiles=prof_repo, taxonomy=TAX, clock=FixedClock(NOW))
    assert p.as_of == NOW and prof_repo.latest() == p and count(db_engine, "profile_snapshots") == 1

def test_rebuild_with_no_observations(db_engine):
    p = rebuild_profile(observations=ObservationRepository(db_engine),
                        profiles=ProfileRepository(db_engine, TAX), taxonomy=TAX, clock=FixedClock(NOW))
    assert p.entries == ()
```

```python
# tests/test_cli.py  (monkeypatch NOSOLEAR_DATA_DIR to tmp_path)
def test_dev_seed_then_rebuild(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("NOSOLEAR_DATA_DIR", str(tmp_path))
    assert main(["db", "upgrade"]) == 0
    assert main(["dev-seed", "--days", "14", "--seed", "7"]) == 0
    assert "Rebuilt profile: 6 keys" in capsys.readouterr().out

def test_dev_seed_refuses_existing_data(tmp_path, monkeypatch):
    monkeypatch.setenv("NOSOLEAR_DATA_DIR", str(tmp_path))
    main(["db", "upgrade"]); main(["dev-seed"])
    assert main(["dev-seed"]) == 2

def test_seed_is_deterministic():
    assert seed_observations(days=14, seed=7, end=NOW) == seed_observations(days=14, seed=7, end=NOW)
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `uv run pytest tests/app tests/test_cli.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement** the ports, adapter, use case, seed and CLI to the interfaces above. The seed uses `random.Random(seed)` with miss rates that fall over the window, so the profile page has trends to show.

- [ ] **Step 4: Run all API tests and confirm they pass**

Run: `uv run pytest -q && uv run pyright`
Expected: all pass.

- [ ] **Step 5: Commit, open the PR, and merge when green**

```bash
git switch -c p0a/06-rebuild-cli
git add apps/api Makefile
git commit -m "Add profile rebuild use case and CLI"
git push -u origin HEAD && gh pr create --fill && gh pr checks --watch && gh pr merge --squash --delete-branch
```

---

### Task 7: Profile API and the OpenAPI contract

**Files:**
- Create:
  - `apps/api/src/nosolear/api/deps.py`, `schemas.py`, `profile_routes.py`, `export_openapi.py`
  - `apps/web/src/shared/api/openapi.json` (generated), `apps/web/src/shared/api/schema.d.ts` (generated)
- Modify:
  - `apps/api/src/nosolear/api/app.py` (a lifespan that runs `upgrade_to_head`, plus the router)
  - `apps/web/package.json` (add `openapi-typescript` and a `gen:api` script)
  - `.github/workflows/ci.yml` (add the `contract` job)
  - `Makefile` (add a `gen-api` target)
- Test: `apps/api/tests/api/test_profile_api.py`

**Interfaces:**
- **Consumes:** `ProfileRepository.latest()` (Task 5); `TAXONOMY_VERSION` and `ALGO_VERSION`.
- **Produces:**
  - `ProfileEntryOut` with fields:
    - `error_key: str`
    - `skill: Literal["sounds","on_the_spot","articulate"]`
    - `family: str`, `description: str`, `impact: int`
    - `p_hat: float`, `ci_low: float`, `ci_high: float`, `n_eff: float`
    - `status: Literal["unknown","active","improving","watching","mastered"]`
    - `priority: float`, `last_seen_at: datetime`
  - `ProfileOut` with fields `as_of: datetime | None`, `taxonomy_version: int`, `algo_version: int`, `entries: list[ProfileEntryOut]`.
  - `GET /api/profile` returns `ProfileOut`, with `operation_id="getProfile"`. Entries come in the stored priority order. An empty database returns `as_of: null, entries: []`.
  - `deps.get_profile_repository(settings) -> ProfileRepository`, overridable in tests.
  - `python -m nosolear.api.export_openapi` prints `json.dumps(create_app().openapi(), indent=2, sort_keys=True)` followed by a newline. It must not touch the database.
  - CI job `contract`:
    1. Set up uv and pnpm.
    2. Export the schema to `apps/web/src/shared/api/openapi.json`.
    3. Run `pnpm --dir apps/web gen:api`, which runs `openapi-typescript src/shared/api/openapi.json -o src/shared/api/schema.d.ts`.
    4. Run `git diff --exit-code`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/test_profile_api.py
def test_profile_empty_db(client_with_tmp_db):
    r = client_with_tmp_db.get("/api/profile")
    assert r.status_code == 200
    assert r.json() == {"as_of": None, "taxonomy_version": 1, "algo_version": 1, "entries": []}

def test_profile_returns_entries_in_priority_order(client_with_tmp_db, seeded_profile):
    body = client_with_tmp_db.get("/api/profile").json()
    assert [e["error_key"] for e in body["entries"]] == [e.definition.key for e in seeded_profile.entries]
    first = body["entries"][0]
    assert first["status"] in {"unknown", "active", "improving", "watching", "mastered"}
    assert set(first) == {"error_key", "skill", "family", "description", "impact", "p_hat", "ci_low",
                          "ci_high", "n_eff", "status", "priority", "last_seen_at"}

def test_openapi_operation_id():
    assert create_app().openapi()["paths"]["/api/profile"]["get"]["operationId"] == "getProfile"
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `uv run pytest tests/api -q`
Expected: FAIL (404 on `/api/profile`).

- [ ] **Step 3: Implement** the routes, schemas, dependencies and export script. Then generate `openapi.json` and `schema.d.ts` with `make gen-api`.

- [ ] **Step 4: Run the tests and the drift check, and confirm they pass**

Run: `uv run pytest -q && make gen-api && git diff --exit-code apps/web/src/shared/api`
Expected: tests pass; the second `gen-api` run produces no diff.

- [ ] **Step 5: Commit, open the PR, merge when green, and add `contract` to the required checks**

```bash
git switch -c p0a/07-profile-api
git add apps/api apps/web .github Makefile
git commit -m "Add profile API with generated TypeScript contract"
git push -u origin HEAD && gh pr create --fill && gh pr checks --watch && gh pr merge --squash --delete-branch
gh api -X PATCH repos/shreyandhawa/nosolear/branches/main/protection/required_status_checks \
  -f 'contexts[]=hygiene' -f 'contexts[]=api' -f 'contexts[]=web' -f 'contexts[]=contract'
```

---

### Task 8: Profile page

**Files:**
- Create:
  - `apps/web/src/shared/api/client.ts`
  - `apps/web/src/features/progress/ProfilePage.tsx`, `useProfile.ts`, `formatRate.ts`, `statusLabel.ts`
  - `apps/web/src/test/server.ts`
- Modify:
  - `apps/web/src/app/router.tsx` (add the `/profile` route and nav links)
  - `apps/web/vite.config.ts` (proxy `/api` to `http://127.0.0.1:8000`)
  - `apps/web/src/test/setup.ts` (start MSW)
  - `apps/web/package.json` (add `msw`)
- Test: `src/features/progress/formatRate.test.ts`, `src/features/progress/ProfilePage.test.tsx`

**Interfaces:**
- **Consumes:** `paths` and `components` from `schema.d.ts` (Task 7).
- **Produces:**
  - `api = createClient<paths>({ baseUrl: "" })` in `shared/api/client.ts`.
  - `useProfile()` runs a TanStack Query with key `["profile"]` that calls `api.GET("/api/profile")` and throws on a non-2xx response.
  - `formatRate(p: number, low: number, high: number): string` formats whole percents with `Math.round` and an en dash.
  - `statusLabel(s): string` maps:
    - `unknown` → "Not enough data"
    - `active` → "Active"
    - `improving` → "Improving"
    - `watching` → "Watching"
    - `mastered` → "Mastered"
  - `ProfilePage` renders a table with columns *Problem* (description), *Skill*, *Status*, *Miss rate* and *Evidence* (`n_eff` rounded), in API order.

- [ ] **Step 1: Write the failing tests**

```ts
// formatRate.test.ts
test.each([
  [0.25, 0.17, 0.34, "25% (17–34%)"],
  [0.004, 0, 0.012, "0% (0–1%)"],
])("formatRate(%s, %s, %s) = %s", (p, lo, hi, out) => expect(formatRate(p, lo, hi)).toBe(out));
```

```tsx
// ProfilePage.test.tsx  (renders inside AppProviders; MSW handlers per test)
test("shows the empty state", async () => {
  server.use(http.get("/api/profile", () => HttpResponse.json({ as_of: null, taxonomy_version: 1, algo_version: 1, entries: [] })));
  renderWithProviders(<ProfilePage />);
  expect(await screen.findByText("No practice data yet. Your baseline will fill this in.")).toBeInTheDocument();
});

test("lists entries in API order with status and rate", async () => {
  server.use(http.get("/api/profile", () => HttpResponse.json(PROFILE_FIXTURE)));  // v.w first: active, 0.25 (0.17–0.34)
  renderWithProviders(<ProfilePage />);
  const rows = await screen.findAllByRole("row");
  expect(within(rows[1]).getByText("/v/ said as /w/")).toBeInTheDocument();
  expect(within(rows[1]).getByText("Active")).toBeInTheDocument();
  expect(within(rows[1]).getByText("25% (17–34%)")).toBeInTheDocument();
});

test("shows an error when the API fails", async () => {
  server.use(http.get("/api/profile", () => new HttpResponse(null, { status: 500 })));
  renderWithProviders(<ProfilePage />);
  expect(await screen.findByText("Couldn't load your profile. Is the API running?")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `cd apps/web && pnpm test --run`
Expected: FAIL (the modules don't exist yet).

- [ ] **Step 3: Implement** the client, hook, helpers, page and route to the interfaces above.

- [ ] **Step 4: Run all web checks and confirm they pass**

Run: `pnpm lint && pnpm typecheck && pnpm test --run && pnpm build`
Expected: all pass.

- [ ] **Step 5: Check it by hand against synthetic data**

```bash
NOSOLEAR_DATA_DIR=$PWD/data/dev uv --directory apps/api run nosolear db upgrade
NOSOLEAR_DATA_DIR=$PWD/data/dev uv --directory apps/api run nosolear dev-seed
NOSOLEAR_DATA_DIR=$PWD/data/dev make api   # terminal 1
make web                                    # terminal 2 → http://localhost:5173/profile
```

Expected: six rows sorted by priority, each showing a status and a rate with its interval. No console errors.

- [ ] **Step 6: Commit, open the PR, and merge when green**

```bash
git switch -c p0a/08-profile-page
git add apps/web
git commit -m "Add profile page backed by the generated API client"
git push -u origin HEAD && gh pr create --fill && gh pr checks --watch && gh pr merge --squash --delete-branch
```

---

## Done when

- `main` is protected and requires `hygiene`, `api`, `web` and `contract`.
- `make test` passes locally.
- With dev-seeded data, `/profile` shows a ranked error list with statuses and intervals.
- No code path calls a network service.
- Phase 0c then adds real detectors that produce `Observation`s; nothing downstream of `make_observation` changes.
