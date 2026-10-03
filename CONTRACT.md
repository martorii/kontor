# Kontor — Contract

This file records the decisions agreed during scoping. It is the source of truth for **what** Kontor does.
`PLAN.md` describes **how and in which order** it gets built.

A decision changes only when the developer explicitly decides so. Every change is recorded in the changelog at the bottom.

---

## 1. Product

- **1.1** The app is called **Kontor**.
- **1.2** Kontor ingests bank transaction CSV files, assigns each transaction a category, stores everything in a database, and shows spending insights.
- **1.3** Kontor runs on localhost for a single user. There is no authentication.
- **1.4** Kontor is built with production best practices: typed code, tests, CI, versioned images, migrations, structured logging.
- **1.5** v2 adds a text-to-SQL agent (LangGraph, local LLM). v1 does not build it, but v1 keeps the schema clean and exposes reporting SQL views that the agent will query.

## 2. Stack

- **2.1** The backend is a FastAPI application in Python, managed with **uv** and configured through `pyproject.toml`.
- **2.2** Code quality is enforced with **ruff** (lint + format), **mypy**, and **pytest**.
- **2.3** The frontend is **Streamlit**. It is a thin client: it talks to the API over HTTP only, and contains no business logic and no database access.
- **2.4** The database is **PostgreSQL**. Every schema change goes through an **Alembic** migration.
- **2.5** The LLM runs locally in **LM Studio** on the host machine and is reached through its OpenAI-compatible API.
- **2.6** The code follows a **hexagonal (ports-and-adapters)** architecture. The domain has no I/O; databases, parsers, the LLM, and the rules file are adapters behind ports.
- **2.7** Logging uses **structlog**: readable console output by default, JSON output switchable through one environment variable.
- **2.8** Kontor is deployed with **Docker Compose**. Services:
  - `postgres`
  - `migrate` — one-shot; runs Alembic migrations
  - `api` — starts only after `migrate` has completed successfully
  - `ui`
- **2.9** Library choices not listed in this contract are proposed in the plan step that introduces them, and confirmed by the developer.

## 3. Banks and parsing

- **3.1** v1 supports **DKB**. The DKB format details are defined during implementation.
- **3.2** Each bank format is one parser in a **parser registry**. A parser detects whether it recognizes a file from its header, and maps rows to one canonical transaction schema. Adding a bank means adding one parser plus its fixture tests.
- **3.3** The original CSV row is stored as JSONB next to the canonical fields, so transactions can be re-parsed without re-uploading.

## 4. Accounts

- **4.1** Kontor supports multiple accounts and multiple bank providers.
- **4.2** An upload is matched to its account by the **IBAN found in the file**.
- **4.3** When the IBAN matches no existing account, Kontor **creates the account automatically**: bank and account type come from the parser, and the name gets a default. Every account field can be edited afterwards through the API and the UI.

## 5. Categories

- **5.1** Categories form a **two-level tree**: top-level category → subcategory. The concrete tree is defined during implementation.
- **5.2** The tree is defined in the YAML file together with the rules. Each category has a stable slug ID (e.g. `food.groceries`).
- **5.3** The tree is synced into a `categories` table at startup. Transactions reference categories by foreign key.
- **5.4** Every top-level category has a **kind**: `expense`, `income`, `transfer`, or `savings`. Spending reports count only `expense`. Income vs. expenses excludes `transfer` and `savings`.
- **5.5** Each transaction has **exactly one** category, or none (uncategorized). Split transactions are not part of v1.

## 6. Rules

- **6.1** Rules are stored in a YAML file. The **developer edits the YAML by hand**. Kontor reads the file and never writes to it.
- **6.2** Rules are ordered, and the **first matching rule wins**.
- **6.3** A rule matches on one field:
  - counterparty name
  - purpose (Verwendungszweck)
  - counterparty IBAN
- **6.4** Match types:
  - `contains` — case-insensitive; the default
  - `regex`
- **6.5** A rule can add optional conditions: amount sign, amount range, account.
- **6.6** Matching runs on **normalized** text: uppercased, with store numbers, dates, and boilerplate stripped.
- **6.7** Fuzzy matching is **never** used to assign a category automatically.
- **6.8** The YAML is validated with Pydantic on every load. If the file is invalid, the reload is rejected and the previously loaded rules stay active.
- **6.9** The real `rules.yaml` is gitignored and mounted into the container. The repo contains a `rules.example.yaml` with generic rules.

## 7. Categorization pipeline

- **7.1** Order: **rules → LLM → uncategorized**.
- **7.2** The LLM sees only transactions that no rule matched.
- **7.3** The LLM's output is constrained to the category list through a JSON schema, and comes with a confidence score.
- **7.4** Below a configurable confidence threshold, the LLM's answer is stored as a **suggestion**, and the transaction stays uncategorized.
- **7.5** Uncategorized transactions are stored in the database and resolved later in the review tab.
- **7.6** Every categorization records its provenance:
  - source (`rule`, `llm`, or `manual`)
  - rule ID
  - hash of the rules file
  - model name
  - confidence
  - timestamp

  The current category and its source are stored on the transaction. The full history, including suggestions that were not applied, is stored in `categorization_events`.
- **7.7** **Manual categorizations are never overwritten** by rules or by the LLM.
- **7.8** `POST /categorization/rerun` re-applies the rules:
  - It reloads and validates the YAML first.
  - It re-evaluates uncategorized, rule-categorized, and LLM-categorized transactions.
  - A matching rule replaces an LLM categorization. Without a match, the LLM result stays.
  - Manual categorizations are untouched.
  - `dry_run=true` returns the changes without writing them.
- **7.9** The LLM is not re-run automatically on old transactions. A separate endpoint runs the LLM step on currently uncategorized transactions on demand, for example after LM Studio was offline.

## 8. Import

- **8.1** The user uploads a CSV through the UI. The UI sends it to the API.
- **8.2** The upload request is **synchronous**: the request returns once parsing, rules, and the LLM step are done.
- **8.3** Parse, deduplicate, rule-categorize, and persist happen in **one database transaction**, which is committed before the LLM step starts. A failure in this phase rolls back the whole file.
- **8.4** LLM results are written in small committed batches. An interruption leaves the remaining transactions uncategorized and loses no imported data.
- **8.5** Before the LLM step, Kontor checks that LM Studio is reachable. If it is not, the step is skipped with one warning log line, and the import still succeeds.
- **8.6** Each LLM call has a timeout. The number of concurrent LLM calls is configurable and defaults to 1.
- **8.7** The LLM step logs one line per transaction in the `api` container:
  - import ID
  - progress (`n/N`)
  - counterparty
  - assigned category
  - confidence
  - latency

  A summary line closes the step.
- **8.8** Every upload is recorded in an `imports` table: account, file name, file hash, timestamp, status, and counts (new, duplicates, rule-matched, LLM-matched, uncategorized).

## 9. Idempotency

- **9.1** The **file hash** is unique. Uploading the same file twice is rejected.
- **9.2** Every transaction has a **fingerprint**: SHA-256 over account, booking date, amount, normalized counterparty, purpose, and an **occurrence index** within identical (date, amount, text) groups. The fingerprint is unique per account.
- **9.3** Overlapping exports import only the transactions that are not stored yet. Genuinely identical transactions on the same day stay separate rows.

## 10. Data model

- **10.1** Tables:

  | Table | Contents |
  |---|---|
  | `accounts` | name, bank, IBAN, currency, account type, parser format |
  | `imports` | see 8.8 |
  | `transactions` | account, import, booking date, value date, amount, currency, counterparty (raw, normalized, IBAN), purpose, fingerprint, raw row (JSONB), current category, current category source |
  | `categories` | slug, parent, name, kind |
  | `categorization_events` | see 7.6 |

- **10.2** Amounts are stored as `NUMERIC(12,2)`. Negative amounts are outflows. Money is never handled as `float` in code.
- **10.3** The normalized counterparty is stored as its own column, written at import time.

## 11. Reports and UI (v1)

- **11.1** v1 contains these views:
  1. **Monthly overview** — spending per top-level category per month, with drill-down to subcategories
  2. **Year view / comparison** — totals per category for a year, compared with the previous year
  3. **Income vs. expenses** — monthly income, expenses, net, and savings rate
  4. **Top merchants** — spending by normalized counterparty
  5. **Transaction explorer** — filterable by account, date range, category, text, and categorization source
  6. **Review tab** — uncategorized transactions and LLM suggestions, assigned manually
  7. **Import history** — each upload with its counts and status
- **11.2** The UI also lets the user view and edit accounts.
- **11.3** Aggregations live in **FastAPI endpoints backed by SQL views**, not in Streamlit. The views are tested with pytest against Postgres.
- **11.4** Budgets, recurring-payment detection, and running balances are not part of v1.

## 12. Testing and evaluation

- **12.1** The LLM sits behind a port, with an LM Studio adapter and a **fake adapter**. CI tests the categorization pipeline with the fake adapter.
- **12.2** Tests that call the real LM Studio are marked `@pytest.mark.llm`. They are skipped by default and run locally with `make test-llm`.
- **12.3** `make eval` runs a labeled set through the categorizer and writes a JSON result file containing:
  - top-level accuracy
  - subcategory accuracy
  - coverage at the confidence threshold
  - accuracy of the categorized transactions
  - average latency
  - model name
  - prompt hash
- **12.4** The labeled set is exported from manual categorizations. The export is gitignored.
- **12.5** Running the eval in CI is not part of v1.

## 13. CI/CD and workflow

- **13.1** GitHub Actions runs on every pull request:
  - ruff (lint and format check)
  - mypy
  - pytest against a Postgres service container
  - an Alembic check that migrations apply and match the models
  - a Docker image build
- **13.2** `main` is protected. A merge requires all checks to pass.
- **13.3** Each plan step is developed on its own branch and merged into `main` through a pull request once its pass gate is met.
- **13.4** Commits follow **Conventional Commits**. **release-please** creates semantic version tags and a changelog.
- **13.5** A release builds versioned images and pushes them to **GHCR**.
- **13.6** Local deployment is `make deploy`, which runs `docker compose pull && docker compose up -d` against pinned image tags. Rollback means pinning the previous tag.
- **13.7** Postgres data lives in a named Docker volume that survives redeploys.

## 14. Data protection

- **14.1** No real financial data is ever committed: no real CSV exports, no real `rules.yaml`, no eval exports, no `.env`.
- **14.2** Test fixtures are synthetic: fake names, fake IBANs.
- **14.3** **gitleaks**, or an equivalent IBAN-pattern check, runs as a pre-commit hook and in CI.
- **14.4** Kontor has **no backup service**. This is an accepted risk. Recovery means re-importing the CSV exports, which restores everything except manual categorizations.

## 15. Open items

These are decided during implementation and then moved into the sections above:

- **15.1** The concrete category tree.
- **15.2** The DKB CSV format details: checking account, and the credit card if used.
- **15.3** How an account is identified for future formats that contain no IBAN.
- **15.4** The default LLM confidence threshold.
- **15.5** Whether the repo is public or private.

---

## Changelog

- **2026-10-03** — Initial contract from scoping.
