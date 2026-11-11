.PHONY: setup api test lint

setup:
	cd apps/api && uv sync
	git config core.hooksPath scripts/git-hooks

api:
	cd apps/api && uv run uvicorn nosolear.api.app:create_app --factory --reload --port 8000

test:
	cd apps/api && uv run pytest -q

lint:
	cd apps/api && uv run ruff check && uv run ruff format --check && uv run pyright
