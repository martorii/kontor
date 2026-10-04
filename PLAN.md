# Kontor — Implementation Plan

This plan builds `CONTRACT.md` step by step. The developer guides every step. No step starts before the previous one is merged.

## Rules for every step

1. Create the branch `step-NN-<slug>` from an up-to-date `main`.
2. Implement only what the step's scope lists. Anything else becomes a note for a later step.
3. Make the step's **pass gate** green. CI must also be green; this applies from Step 02 on.
4. Open a pull request and merge it into `main`.
5. If a decision changed, update `CONTRACT.md` and its changelog in the same PR.
6. Tick the step's box below.

---

## Phase A — Foundation

### Step 01 — Repository bootstrap
- [x] **Scope**
  - uv project with `pyproject.toml` and a `src/kontor` layout (see `CLAUDE.md`)
  - ruff, mypy (strict), and pytest configured
  - `.gitignore` covering `.env`, `config/rules.yaml`, `data/`, and eval exports
  - pre-commit hooks: ruff, mypy, gitleaks
  - a `Makefile` with `lint`, `format`, `typecheck`, `test`
  - `CONTRACT.md`, `PLAN.md`, and `CLAUDE.md` committed
- **Pass gate**
  - `make lint typecheck test` passes, with one smoke test.
  - `pre-commit run --all-files` passes.

### Step 02 — CI pipeline
- [x] **Scope**
  - GitHub Actions workflow running ruff, the format check, mypy, pytest, and gitleaks on every PR
  - branch protection on `main` requiring these checks
- **Pass gate**
  - The PR for this step shows all checks green.
  - A deliberately failing commit, pushed and then reverted, blocks the merge.

### Step 03 — API skeleton, configuration, logging
- [x] **Scope**
  - FastAPI app factory
  - settings via environment variables (a `.env.example` is committed)
  - structlog setup: console output by default, JSON switchable by env var
  - `GET /health`
- **Pass gate**
  - A test calls `/health` and gets 200.
  - A test asserts that the JSON log mode emits valid JSON.

### Step 04 — Docker Compose and Postgres
- [x] **Scope**
  - a multi-stage Dockerfile for the API, built with uv
  - `docker-compose.yml` with `postgres` and `api`, both with health checks
  - a named volume for the Postgres data
  - CI builds the image
- **Pass gate**
  - `docker compose up` brings both services to healthy.
  - `curl localhost:<port>/health` returns 200.
  - The CI image build is green.

### Step 05 — Database schema and migrations
- [x] **Scope**
  - SQLAlchemy models for the tables in CONTRACT §10
  - an initial Alembic migration
  - the one-shot `migrate` service in compose; `api` depends on it
  - a pytest Postgres fixture
  - a CI check for migration drift
- **Pass gate**
  - `alembic upgrade head` succeeds on an empty database.
  - The drift check passes in CI.
  - A test inserts and reads one row per table.

### Step 06 — Release and CD pipeline
- [x] **Scope**
  - release-please workflow
  - on each release, build and push the images to GHCR, tagged with the version
  - compose uses pinned image tags
  - `make deploy` and `make rollback TAG=…`
- **Pass gate**
  - Merging this step produces a release PR.
  - Merging the release PR creates `v0.1.0`, and the image appears in GHCR.
  - `make deploy` runs that tag locally, and `/health` returns 200.

## Phase B — Ingestion

### Step 07 — Domain core
- [x] **Scope**
  - the canonical transaction model (amounts as `Decimal`)
  - counterparty and purpose normalization
  - fingerprinting with the occurrence index
  - all of it pure domain code, with no I/O
- **Pass gate** — unit tests cover:
  - normalization cases
  - fingerprint stability
  - two identical transactions on the same day producing distinct fingerprints
  - overlapping input producing identical fingerprints for the shared rows

### Step 08 — Parser registry and DKB parser
- [x] **Scope**
  - the parser port and the registry with header-based detection
  - the DKB parser, including IBAN extraction from the file
  - synthetic DKB fixtures
  - an unknown format raises a clear error
- **Pass gate** — tests cover:
  - detection
  - fixture → canonical rows (field by field)
  - IBAN extraction
  - malformed-file and unknown-format errors

### Step 09 — Import service and accounts
- [x] **Scope**
  - `POST /imports`: file hash check, account matching and auto-creation by IBAN, deduplication, persistence in one DB transaction, an `imports` record with counts
  - `GET` and `PATCH` endpoints for accounts
- **Pass gate** — integration tests cover:
  - a first import
  - the same file rejected
  - an overlapping file inserting only new rows
  - an unknown IBAN creating an account
  - a parse error rolling back the whole file

## Phase C — Categorization

### Step 10 — Category tree and rules YAML
- [ ] **Scope**
  - the Pydantic schema for categories and rules
  - the YAML loader (port + adapter)
  - category sync into the DB at startup
  - `config/rules.example.yaml`
  - the concrete category tree is defined (CONTRACT §15.1)
- **Pass gate** — tests cover:
  - invalid YAML rejected with a readable error
  - the category sync being idempotent
  - a missing parent or a duplicate slug rejected

### Step 11 — Rule engine in the import
- [ ] **Scope**
  - the rule engine: field, match type, and conditions; first match wins
  - integrated into the import
  - writes `categorization_events` with provenance
- **Pass gate** — tests cover:
  - each match type and field
  - each condition
  - rule ordering
  - the provenance stored correctly
  - unmatched transactions left uncategorized

### Step 12 — Re-categorization endpoint
- [ ] **Scope**
  - `POST /categorization/rerun` with `dry_run`, following CONTRACT §7.8
- **Pass gate** — tests cover:
  - manual categorizations untouched
  - a rule replacing an LLM result
  - an LLM result kept when no rule matches
  - dry run writing nothing
  - an invalid YAML keeping the old rules active

### Step 13 — LLM adapter
- [ ] **Scope**
  - the LLM port, the LM Studio adapter (JSON-schema output, health check, timeout), and the fake adapter
  - the confidence threshold setting
  - the default threshold is decided (CONTRACT §15.4)
- **Pass gate**
  - CI tests pass with the fake adapter: valid output, a category outside the list rejected, timeout handling.
  - `make test-llm` passes locally against LM Studio.

### Step 14 — LLM in the import flow
- [ ] **Scope**
  - the LLM step after the commit, writing in batches
  - per-transaction and summary log lines (CONTRACT §8.7)
  - skip when LM Studio is down
  - configurable concurrency
  - the on-demand LLM endpoint (CONTRACT §7.9)
- **Pass gate**
  - Tests cover: below-threshold results stored as suggestions; LM Studio unreachable → the import succeeds with one warning; an interruption mid-step keeps the imported rows.
  - A manual check shows the log lines in `docker compose logs -f api`.

### Step 15 — Manual categorization API
- [ ] **Scope**
  - endpoints to list uncategorized transactions with their suggestions, and to set a category manually (as an override)
- **Pass gate** — tests cover:
  - a manual override recorded with source `manual`
  - the override surviving a rerun
  - the suggestions returned with their confidence

## Phase D — Reporting and UI

### Step 16 — Reporting views and endpoints
- [ ] **Scope**
  - SQL views (in migrations) and endpoints for: monthly overview, year comparison, income vs. expenses, top merchants
  - a transaction explorer query with filters
- **Pass gate**
  - Tests on seeded data assert exact totals.
  - Tests assert that `transfer` and `savings` are excluded from spending.
  - Tests assert that the filters work.

### Step 17 — Streamlit shell, upload, import history, accounts
- [ ] **Scope**
  - the `ui` service in compose
  - an API client module
  - pages for upload (showing the import summary), import history, and accounts (view and edit)
- **Pass gate**
  - Manual: upload a synthetic DKB file end to end, see the summary and the new account, rename the account.
  - The UI code contains no DB access.

### Step 18 — Streamlit report views
- [ ] **Scope**
  - monthly overview with drill-down
  - year comparison
  - income vs. expenses
  - top merchants
- **Pass gate** — Manual: each view's numbers match the API responses for the seeded data.

### Step 19 — Streamlit review tab and transaction explorer
- [ ] **Scope**
  - the review tab: uncategorized transactions and suggestions, one-click assignment
  - the transaction explorer with filters
  - a button to trigger a rerun, with a dry-run preview
- **Pass gate** — Manual: categorize a transaction from the review tab; it disappears from the review list and shows up in the reports.

## Phase E — Evaluation and release

### Step 20 — Evaluation harness
- [ ] **Scope**
  - an export of manual categorizations into a gitignored labeled set
  - `make eval` writing a JSON result file (CONTRACT §12.3)
- **Pass gate** — `make eval` runs locally and produces a result file with every metric filled in.

### Step 21 — v1 release
- [ ] **Scope**
  - a README with setup from a fresh clone: LM Studio, `rules.yaml`, `.env`, `make deploy`
  - CONTRACT §15 cleaned up
  - release `v1.0.0`
- **Pass gate** — A fresh clone, following only the README, runs Kontor from the GHCR images, and an import works end to end.
