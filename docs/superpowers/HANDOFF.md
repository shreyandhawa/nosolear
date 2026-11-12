# Handoff

Read this first in a new session, then continue from **Next**.

## Current phase

Re-plan for the open-source, bring-your-own-keys direction. Gate 1 of 2: the revised `docs/ARCHITECTURE.md` is in a PR waiting for the owner's approval.

## Done

- 2026-11-12: Surveyed docs, `apps/api`, CI, tooling and the `p0b/spikes` branch.
- 2026-11-12: Baseline on `main` (bea116e) is green. `make test`: 191 API and 10 web tests pass. `make lint`: ruff, ruff format, pyright, eslint and tsc are clean.
- 2026-11-12: Brainstormed the design with the owner. All three sections were approved: approach and components, data flow, and security, errors, testing and phases.

## In progress

- PR from branch `docs/byok-architecture`: the revised `docs/ARCHITECTURE.md`, a superseded banner on the old Phase 0b plan, and this file. **Do not merge without the owner's explicit approval.**

## Next

1. The owner approves the architecture PR. Then squash-merge it.
2. Run `superpowers:writing-plans`: one plan per phase in `docs/superpowers/plans/` (0b, 0c, 0d, 0e, 1), with tasks small enough for one subagent each. Open them as one PR. **Gate 2: stop for the owner's approval.**
3. Execute with `superpowers:subagent-driven-development`: one branch and one PR per task, test first. Run pr-review-toolkit's code-reviewer, silent-failure-hunter and pr-test-analyzer on each PR. Run `/security-review` at the end of each phase, then hand off.

## Decisions and why

| Date | Decision | Why |
|---|---|---|
| 2026-11-12 | Open source, bring your own keys, local only. No accounts, no hosting. | The owner changed direction. |
| 2026-11-12 | MIT licence | Owner's choice. |
| 2026-11-12 | Localhost only. The token-auth mode is designed now and built later. Phone access comes after token mode. | The security rule: never expose the API unauthenticated. The web app can't send a token yet, because apps/web is out of scope. |
| 2026-11-12 | macOS and Linux are first-class. Windows users go through WSL2. CI adds a macOS runner. | Owner's choice. The repo is public, so the macOS runner is free. |
| 2026-11-12 | Approach A: one package. Local models are optional extras (`local`, `apple`) with lazy imports. | Keeps one process and one lockfile. Readiness reports "not installed" instead of crashing. |
| 2026-11-12 | CrisperWhisper is opt-in only. | Its licence is non-commercial. |
| 2026-11-12 | Calibration uses the old S2 method in the app: ≥80% hits, ≤20% false alarms, at least 5 error tokens and 5 controls per key. It's skippable; until then, scores are provisional. | The goal's "calibrate, then baseline, then daily". |
| 2026-11-12 | Scope is the old Phase 0 build plus the Phase 1 daily-loop backend. Drills, live conversation, re-test and the web UI come later. | Goal item 6. |
| 2026-11-12 | The target accent stays en-US, with the locale as a setting. The coach defaults to `claude-opus-5-5` and is configurable. | Earlier decisions, kept. |
| 2026-11-12 | Keep `p0b/spikes`. Salvage `common.py`, `phones.py`, `tts_controls.py` and `items.py` into `apps/api`, inside the tasks that need them. | The owner's rule against deleting branches. That code is already debugged. |

## Open questions for the owner

None right now.

## Branch and PR state

- `main`: bea116e "Fix final-review findings for Phase 0a (#11)".
- `docs/byok-architecture`: the architecture revision PR (gate 1).
- `p0b/spikes`: unmerged, kept. Two commits, all under `spikes/`. No audio or data files.

## Adapters not yet verified against the live service

None are built yet. Every adapter starts unverified. Live checks need the owner to put Azure and Claude keys in `.env`; never ask for a key in chat.

## Working rules carried forward

- Hand off at about 35–40% context, at a task boundary, and at the end of every phase.
- Commits: imperative sentence. No Co-Authored-By trailer. No "Generated with Claude Code" footer.
- Commit and push to the feature branch as you go. Never push to `main`. Squash-merge task PRs once CI is green and a non-author reviewer approves. Gate PRs wait for the owner.
- Models: haiku for search, summaries and running tests; sonnet for well-specified implementation and routine review; opus for architecture, security review and final review. If a cheaper model fails review twice, re-dispatch on a stronger one.

## Verify the current state

```bash
make setup   # first time only: uv sync, pnpm install, git hooks
make test
make lint
```
