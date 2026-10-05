.PHONY: lint format format-check typecheck test test-llm migrate-check deploy rollback reset-db

lint:
	uv run ruff check .

format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

typecheck:
	uv run mypy src tests ui

test:
	uv run pytest

# Needs LM Studio running locally (LLM_BASE_URL, LLM_MODEL in .env).
test-llm:
	uv run pytest -m llm

# Fails if the models and the migrations disagree. Needs a migrated, reachable DATABASE_URL.
migrate-check:
	uv run alembic upgrade head
	uv run alembic check

# Run the pinned release images (KONTOR_TAG in .env, default kept current by release-please).
deploy:
	docker compose pull
	docker compose up -d

# Pin a previous release: make rollback TAG=vX.Y.Z
rollback:
	@test -n "$(TAG)" || { echo "usage: make rollback TAG=vX.Y.Z"; exit 1; }
	@touch .env
	@grep -v '^KONTOR_TAG=' .env > .env.tmp || true
	@echo 'KONTOR_TAG=$(TAG)' >> .env.tmp
	@mv .env.tmp .env
	$(MAKE) deploy

# Deletes ALL data (named volume, no backups: CONTRACT §14.4), then recreates the schema.
reset-db:
	@printf "This deletes ALL Kontor data and cannot be undone. Type 'reset' to continue: "; \
	read answer; test "$$answer" = "reset" || { echo "aborted"; exit 1; }
	docker compose down -v
	docker compose up -d
