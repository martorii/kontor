.PHONY: lint format format-check typecheck test migrate-check deploy rollback

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
