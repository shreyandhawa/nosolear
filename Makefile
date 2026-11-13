.PHONY: setup api api-dev web seed test test-live lint gen-api

setup:
	git config core.hooksPath scripts/git-hooks
	cd apps/api && uv sync
	cd apps/web && pnpm install

api:
	cd apps/api && uv run nosolear serve --reload

api-dev:
	cd apps/api && NOSOLEAR_DATA_DIR=$(CURDIR)/data/dev uv run nosolear serve --reload

web:
	cd apps/web && pnpm dev

seed:
	cd apps/api && export NOSOLEAR_DATA_DIR=$(CURDIR)/data/dev && uv run nosolear db upgrade && uv run nosolear dev-seed

test:
	cd apps/api && uv run pytest -q
	cd apps/web && pnpm test --run

test-live:
	cd apps/api && uv run pytest -q -m live

lint:
	cd apps/api && uv run ruff check && uv run ruff format --check && uv run pyright
	cd apps/web && pnpm lint && pnpm typecheck

gen-api:
	mkdir -p apps/web/src/shared/api
	cd apps/api && uv run python -m nosolear.api.export_openapi > ../web/src/shared/api/openapi.json
	cd apps/web && pnpm gen:api
