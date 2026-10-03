# CLAUDE.md — Kontor

Kontor is a local, single-user app. It ingests bank CSV exports, categorizes each transaction (rules → local LLM → manual review), stores everything in Postgres, and shows spending reports. v2 adds a text-to-SQL agent.

## Source of truth

- `CONTRACT.md` — what Kontor does. Every agreed decision lives here. Do not contradict it. If a task requires deviating from it, stop and ask the developer.
- `PLAN.md` — the order of work: numbered steps, each with a scope and a pass gate.

## How we work

- The developer guides the implementation. Work on one plan step at a time, and never start the next step unless the developer says so.
- Before writing code for a step, briefly restate its scope and pass gate, and propose any new library (CONTRACT §2.9). Wait for confirmation.
- Each step gets its own branch, `step-NN-<slug>`, created from an up-to-date `main`. The step is merged into `main` through a PR once its pass gate and CI are green.
- Stay inside the step's scope. Anything else goes into a note, not into the code.
- Commits follow Conventional Commits (`feat:`, `fix:`, `test:`, `chore:`, `docs:`, `ci:`, `refactor:`). release-please depends on this.
- When a decision changes, update `CONTRACT.md` and its changelog in the same PR.
- Never add a dependency without asking.

## Commands

```bash
uv sync                      # install dependencies
make lint                    # uv run ruff check .
make format                  # uv run ruff format .
make typecheck               # uv run mypy src tests
make test                    # uv run pytest (excludes -m llm)
make test-llm                # tests against the real LM Studio (local only)
make eval                    # categorizer evaluation → JSON result file
docker compose up -d         # local stack, built from source
make deploy                  # pull pinned GHCR images and restart
make rollback TAG=vX.Y.Z     # pin a previous release
docker compose logs -f api   # follow API logs, including LLM progress
uv run alembic revision --autogenerate -m "<msg>"
uv run alembic upgrade head
```

Some targets appear only in later plan steps. If a target doesn't exist yet, check `PLAN.md` rather than inventing it.

## Architecture (hexagonal)

```
src/kontor/
  domain/          # entities, value objects, normalization, fingerprint. No I/O, no framework imports.
  application/     # use cases: import, categorize, recategorize, review, reports
  ports/           # Protocols: repositories, parser, rules source, LLM client
  adapters/
    db/            # SQLAlchemy models + repositories
    parsers/       # one module per bank format + registry (dkb.py, ...)
    rules/         # YAML loader + Pydantic schema
    llm/           # lmstudio.py, fake.py
  api/             # FastAPI app factory, routers, request/response schemas
  config.py        # settings from environment
  logging.py       # structlog setup
ui/                # Streamlit app. Talks to the API over HTTP only.
migrations/        # Alembic; SQL views for reports live here too
config/            # rules.example.yaml (real rules.yaml is gitignored)
tests/
  unit/            # domain + application with fakes
  integration/     # Postgres, API, parsers with fixtures
  llm/             # @pytest.mark.llm — real LM Studio
  fixtures/        # synthetic CSVs only
```

Dependencies point inward: `adapters` and `api` depend on `application` and `ports`; `domain` depends on nothing. Wiring happens in the API app factory.

## Conventions

- Money: `Decimal` in code, `NUMERIC(12,2)` in the database. Never `float`. Negative amounts are outflows.
- Typing: mypy strict passes. Every function has full type hints. No `Any` without a comment explaining why.
- Schema: every change goes through a new Alembic migration. Never edit a migration that is already merged.
- Categorization:
  - Manual categorizations are never overwritten.
  - Every categorization writes a `categorization_events` row with its provenance.
  - Fuzzy matching never assigns a category automatically.
- Rules YAML: Kontor reads it and never writes to it. Validate it on every load. An invalid file keeps the previous rules active.
- Logging: use structlog with keyword fields, not f-strings. Every log line during an import carries `import_id`.
- Reports: aggregation logic lives in SQL views and API endpoints, never in Streamlit.
- Errors: raise domain-specific exceptions in `domain` and `application`. Map them to HTTP responses in `api`.

## Testing

- CI runs `make lint typecheck test` plus the migration drift check, the image build, and gitleaks.
- Unit tests use the fake adapters (fake LLM, in-memory repositories where useful). Integration tests use a real Postgres.
- Tests that need LM Studio are marked `@pytest.mark.llm` and are excluded by default.
- Every pass gate in `PLAN.md` is expressed as tests wherever possible. Manual checks are listed explicitly.

## Data protection — hard rules

- Never commit real bank exports, the real `config/rules.yaml`, `.env`, or eval exports.
- Test fixtures are synthetic: fake names and fake IBANs. If you need sample data, generate it.
- Never paste real transaction data into code, tests, comments, or commit messages.

## Environment

- LM Studio runs on the host. Containers reach it at `http://host.docker.internal:<port>/v1` (set in `.env`).
- Postgres data lives in a named volume. `docker compose down -v` deletes all data, and there are no backups (CONTRACT §14.4). Never run it unless the developer asks.
