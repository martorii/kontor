.PHONY: lint format format-check typecheck test migrate-check

lint:
	uv run ruff check .

format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

typecheck:
	uv run mypy src tests

test:
	uv run pytest

# Fails if the models and the migrations disagree. Needs a migrated, reachable DATABASE_URL.
migrate-check:
	uv run alembic upgrade head
	uv run alembic check
