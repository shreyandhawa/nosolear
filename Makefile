.PHONY: setup api web seed test lint gen-api

setup:
	cd apps/api && uv sync
	cd apps/web && pnpm install
	git config core.hooksPath scripts/git-hooks

api:
	cd apps/api && uv run uvicorn nosolear.api.app:create_app --factory --reload --port 8000

web:
	cd apps/web && pnpm dev

seed:
	cd apps/api && uv run nosolear db upgrade && uv run nosolear dev-seed

test:
	cd apps/api && uv run pytest -q
	cd apps/web && pnpm test --run

lint:
	cd apps/api && uv run ruff check && uv run ruff format --check && uv run pyright
	cd apps/web && pnpm lint && pnpm typecheck

gen-api:
	mkdir -p apps/web/src/shared/api
	cd apps/api && uv run python -m nosolear.api.export_openapi > ../web/src/shared/api/openapi.json
	cd apps/web && pnpm gen:api
