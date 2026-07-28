.PHONY: setup check test lint temporal worker run

setup:
	uv sync --dev

check:
	uv run python scripts/check_env.py

test:
	uv run pytest

lint:
	uv run ruff check .

temporal:
	mkdir -p .temporal
	temporal server start-dev --db-filename .temporal/temporal.db

worker:
	uv run python -m worker

run:
	uv run python -m start_workflow
