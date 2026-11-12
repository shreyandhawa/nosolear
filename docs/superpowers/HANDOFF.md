# Handoff

Read this first in a new session, then continue from **Next**.

## Current phase

Phase 0b execution (open-source foundation). Gate 2 is passed: the phase plans PR #13 merged as 391b639.

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

## In progress

- Branch `p0b/05-language-packs`: Task 5, PR open for review. Earlier task PRs may still be open; check `gh pr list`.

## Next

1. Task 6: wire the active pack into the profile. The plan is `docs/superpowers/plans/2026-11-12-phase-0b-open-source-foundation.md`. One branch and one PR per task, with a fresh implementer subagent and a different reviewer subagent each time. Squash-merge on green CI.
2. Any task that adds a dependency reruns `uv run --project apps/api python scripts/third_party_licences.py`.
3. Correct `docs/ARCHITECTURE.md` §17/§18 for the licence discrepancy below.
4. At the end of each phase: run `/security-review`, update this file, and hand off to a fresh session.

## Licence discrepancies found in Task 2

- CrisperWhisper: the code is MIT, but the weights are CC BY-NC 4.0 (`nyralabs/CrisperWhisper`, moved from `nyrahealth/`). Newer Nyra releases use a custom non-commercial research licence. §17 says only "non-commercial"; it should distinguish code (MIT) from weights.
- `mlx-community/whisper-large-v3-turbo` declares no licence on its card; it is a conversion of OpenAI's MIT `large-v3-turbo`. §17 says "confirm"; recorded as such.
- espeak-ng is GPL-3.0 or later (release 1.52.0 at check time), as expected.

## Plans, in execution order

| Phase | File | Tasks | Branch prefix |
|---|---|---|---|
| 0b Open-source foundation | `docs/superpowers/plans/2026-11-12-phase-0b-open-source-foundation.md` | 12 | `p0b/` |
| 0c Audio, jobs, ledger | `docs/superpowers/plans/2026-11-12-phase-0c-audio-jobs-ledger.md` | 11 | `p0c/` |
| 0d Provider adapters | `docs/superpowers/plans/2026-11-12-phase-0d-provider-adapters.md` | 13 | `p0d/` |
| 0e Scoring, calibration, baseline | `docs/superpowers/plans/2026-11-12-phase-0e-scoring-calibration-baseline.md` | 12 | `p0e/` |
| 1 Daily loop backend | `docs/superpowers/plans/2026-11-12-phase-1-daily-loop-backend.md` | 11 | `p1/` |

The Alembic chain after `main`'s 0002:
- 0003 (0b)
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
| 2026-11-12 | CrisperWhisper is opt-in only. | Its licence is non-commercial. |
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

## Open questions for the owner

None right now.

## Branch and PR state

- `main`: 391b639 "Add phase plans 0b–1 for the open-source BYOK backend (#13)".
- `docs/phase-plans`: merged (#13) and kept.
- `p0b/01-community-files`: Task 1 PR.
- `p0b/02-third-party-notices`: Task 2 PR.
- `docs/byok-architecture`: merged and kept (deleting branches needs the owner's approval).
- `p0b/spikes`: unmerged and kept. Everything is under `spikes/`, with no audio and no data.

## Adapters not yet verified against the live service

None are built yet, so every adapter in Phase 0d starts unverified. Live checks need the owner to put the Azure and Claude keys in `.env`; never ask for a key in chat. Update this list as live tests pass.

## Working rules carried forward

- Hand off at about 35–40% context, at a task boundary, and at the end of every phase.
- Commits: imperative sentence. No Co-Authored-By trailer. No "Generated with Claude Code" footer.
- Commit and push to the feature branch as you go. Never push to `main`. Squash-merge task PRs once CI is green and a non-author reviewer approves. Gate PRs wait for the owner.
- Models: haiku for search, summaries and running tests; sonnet for well-specified implementation and routine review; opus for architecture, security review and final review. If a cheaper model fails review twice, re-dispatch on a stronger one.
- Ask the owner for: anything that costs money, deleting branches or data, and approval gates.

## Verify the current state

```bash
make setup   # first time only: uv sync, pnpm install, git hooks
make test
make lint
```
