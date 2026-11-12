# Contributing

Contributions are accepted under the project's MIT licence.

## Setup

```bash
make setup   # uv sync, pnpm install, git hooks
make test
make lint
```

Run `make test` and `make lint` before you push. CI runs the same checks.

## House rules

- **Test first.** Every change starts with a failing test. Commit the test with the code that makes it pass.
- **Branches and PRs.** One branch and one PR per task, named `p<phase>/NN-slug` (for example `p0b/01-community-files`). Keep commits small.
- **Merging.** PRs are squash-merged once CI is green. Never push to `main`.
- **Commit style.** An imperative sentence ("Add the ledger", not "Added" or "Adds"). No trailers and no tool-attribution footers.
- **No real voices.** Fixtures are hand-written. Audio for live tests is generated with Azure TTS and CI audio with espeak-ng. Never commit audio, databases or anything under `data/`.
- **No real keys.** Fixtures hold no keys, not even example values. `.env.example` lists setting names only, with no values.

## Adding a language pack

A language pack is data only: a directory `content/packs/<id>/` with a `pack.toml` and its content files. Check it with:

```bash
cd apps/api && uv run pytest tests/content
```

Open a data-only PR (no code changes) with the new directory.
