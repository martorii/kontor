# Kontor — Implementation Plan (v2: text-to-SQL agent)

This plan builds the v2 agent described in `CONTRACT.md` §16 step by step. The developer guides every step. No step starts before the previous one is merged.

v1 (Steps 01–22) is complete. Its plan lives in the git history of this file.

## Rules for every step

1. Create the branch `step-NN-<slug>` from an up-to-date `main`.
2. Implement only what the step's scope lists. Anything else becomes a note for a later step.
3. Make the step's **pass gate** green. CI must also be green.
4. Open a pull request and merge it into `main`.
5. If a decision changed, update `CONTRACT.md` and its changelog in the same PR.
6. Tick the step's box below.

---

## Phase F — Agent foundations

### Step 23 — v2 contract and plan
- [x] **Scope**
  - `CONTRACT.md` §16 records the agent decisions
  - this `PLAN.md` replaces the v1 plan
- **Pass gate** — The developer approves the PR.

### Step 24 — Read-only role and query executor
- [x] **Scope**
  - an Alembic migration that creates a `NOLOGIN` role `kontor_agent` and grants it to the application user
  - `SELECT` on every table and view in `public`, except `alembic_version`, plus default privileges so future tables and views are covered too
  - a `QueryExecutor` port, with a Postgres adapter that runs each query:
    - in a `READ ONLY` transaction
    - under `SET LOCAL ROLE kontor_agent`
    - with `SET LOCAL statement_timeout` (default 10 s, `AGENT_STATEMENT_TIMEOUT_SECONDS`)
  - the adapter fetches at most `AGENT_MAX_ROWS + 1` rows (default 500) and returns columns, rows, and a `truncated` flag
  - values are typed for JSON: `Decimal` stays `Decimal`, and dates are ISO strings in the API layer
- **Pass gate** (integration tests against Postgres; they call the executor directly, without the validator)
  - `INSERT`, `UPDATE`, `DELETE`, `CREATE`, and `DROP` fail with a permission or read-only error.
  - `SELECT * FROM alembic_version` fails with a permission error.
  - `SELECT pg_sleep(20)` is cancelled by the timeout.
  - A 1,000-row query returns 500 rows with `truncated = true`.
  - The migration drift check stays green.

### Step 25 — SQL validator
- [x] **Scope**
  - a pure validator in `application` (no I/O), built on **sqlglot** (Postgres dialect). This is a new dependency to confirm.
  - it accepts exactly one statement: a `SELECT`, which may use CTEs, `UNION`, or subqueries
  - it rejects:
    - multiple statements
    - DML and DDL
    - `SELECT … INTO`
    - `FOR UPDATE` and `FOR SHARE`
    - `SET`, `COPY`, `CALL`, and `DO`
  - every referenced relation must be in an allowlist that is passed in, and CTE names resolve locally
  - a function denylist: `pg_sleep*`, `pg_read_*`, `pg_ls_dir`, `lo_*`, `dblink*`, `set_config`, `pg_terminate_backend`, `pg_cancel_backend`, `pg_advisory*`, `txid_*`
  - a domain exception `UnsafeQueryError` whose reason is clear enough to feed back to the LLM
- **Pass gate** — A parametrized unit test covers at least 15 accepted and 15 rejected queries, and each rejection asserts its reason.

### Step 26 — Schema context
- [x] **Scope**
  - a `SchemaIntrospector` port with a Postgres adapter, listing the relations, columns (with Postgres types) and single-column foreign keys that `kontor_agent` can `SELECT`
  - `SchemaInfo.allowed_relations` is the validator allowlist
  - the committed notes `src/kontor/agent_notes.md` hold the semantics, contain no real data, and ship inside the package:
    - negative amounts are outflows
    - the flow and refund rules from §11.1a
    - prefer `v_flows` and the report views for spending
    - `counterparty_normalized` is the merchant
    - `category_source` values
  - a rendered schema text, plus a prompt hash: SHA-256 over the system prompt, the notes, and the schema text
  - calling the introspector at startup is wired in Step 28
- **Pass gate**
  - An integration test: the introspected schema lists the `v_flows` columns with their types, includes the foreign keys, and leaves out `alembic_version`. Its allowlist drives `validate_query`.
  - A unit test: the notes load, the rendering is stable, and the hash changes when any of its parts changes.

### Step 26a — Categorizer LLM settings
- [x] **Scope**
  - hard rename of `LLM_*` to `CATEGORIZER_LLM_*`; the old names are no longer read
  - `CATEGORIZER_LLM_BASE_URL` and `CATEGORIZER_LLM_MODEL` are required: the API and `make eval` refuse to start without them, while Alembic does not need them
  - `docker-compose.yml` no longer defaults the URL; `.env.example` sets it explicitly
  - README, Makefile and CONTRACT updated
- **Pass gate**
  - Unit tests: the new names are read and the old ones ignored, and a missing URL or model stops the API and `make eval` with a message that names the variable.
  - Manual: after renaming the variables in `.env`, `make deploy-main-locally` starts and the categorizer is healthy.

## Phase G — The agent

### Step 27 — Agent graph
- [x] **Scope**
  - **langgraph** is a new dependency (confirmed). It pulls in langchain-core and langsmith transitively; our code imports neither, and `LANGSMITH_TRACING=false` is set explicitly. The nodes call LM Studio through the existing `openai` client.
  - settings, explicit and independent of the categorizer's:
    - `AGENT_LLM_BASE_URL` and `AGENT_LLM_MODEL`, required: the API refuses to start without them (checked when the agent is wired, Step 28)
    - `AGENT_LLM_API_KEY`
    - `AGENT_LLM_TIMEOUT_SECONDS`
    - `AGENT_MAX_RETRIES` (default 2)
  - an `AgentLLM` port, with an LM Studio adapter and a scripted fake adapter
  - the graph: `generate_sql → validate → execute → summarize`
    - when validation or execution fails, the loop returns to `generate_sql` with the error, at most `AGENT_MAX_RETRIES` times
    - after the last retry, the agent ends with a `gave_up` status and the last error
  - `summarize` gets the question, the SQL, the columns, and at most `AGENT_SUMMARY_ROWS` rows (default 50). It returns:
    - a short answer in the language of the question
    - a chart spec `{type: bar|line|none, x, y}`
  - the agent checks the chart spec: `x` and `y` must be result columns, and `y` must be numeric. If not, the chart becomes `none`.
  - an in-memory conversation store keyed by `conversation_id`
    - follow-ups see the earlier questions, SQL, and answers, but not the rows
    - at most 10 turns are kept, and a conversation is dropped after 60 minutes idle
  - structlog fields `conversation_id` and `attempt` on every agent log line
- **Pass gate** (unit tests with the fake LLM and a fake executor)
  - Happy path: an answer, the SQL, the rows, and a chart.
  - The first SQL is rejected by the validator, and the second succeeds (`attempts = 2`).
  - Three failures end in `gave_up` and never execute unvalidated SQL.
  - An invalid chart spec becomes `none`.
  - A follow-up turn gets the previous turn in its prompt.
  - An evicted conversation starts fresh.

### Step 28 — Agent API
- [ ] **Scope**
  - `POST /agent/ask` takes `{question, conversation_id?}` and returns:
    - `conversation_id`, `status` (`answered` | `gave_up`)
    - `answer`, `sql`, `columns`, `rows`, `truncated`
    - `chart`, `attempts`
  - `DELETE /agent/conversations/{id}`
  - error mapping:
    - LM Studio unreachable or timed out → 503
    - an empty question → 422
  - wiring in the app factory
- **Pass gate** — API tests with the fake LLM cover each status and each error mapping. The rows round-trip `Decimal` values as strings, and no float conversion happens.

### Step 29 — Streamlit "Ask" tab
- [ ] **Scope**
  - a chat page built with `st.chat_message`: the history of the current session, and a "New conversation" button
  - each answer shows:
    - the summary
    - the result table, with a note when it is truncated
    - the SQL in an expander
    - the chart rendered from the spec, with no logic beyond mapping the spec to `st.bar_chart` or `st.line_chart`
  - a `gave_up` answer shows the last error and the last SQL
- **Pass gate** — Manual, against real data:
  - Ask "How much did I spend on groceries last month?" and get an answer, a table, the SQL, and a chart.
  - The follow-up "and the month before?" resolves against the earlier question.
  - Asking the agent to delete a transaction leaves the data unchanged.

## Phase H — Evaluation and release

### Step 30 — Agent evaluation
- [ ] **Scope**
  - a committed golden set, `tests/agent_eval/golden.yaml`, with at least 25 synthetic questions, each with reference SQL
  - a seed script that loads synthetic fixture data into a scratch database. This is never the real database.
  - **execution accuracy**:
    - compare the result of the generated SQL with the reference result
    - rows are compared as multisets, and in order when the reference uses `ORDER BY`
    - numbers are normalized to `Decimal`, and column names are ignored
  - `make eval-agent` writes `eval_results/agent-<timestamp>.json` with:
    - execution accuracy, validity rate, and give-up rate
    - average attempts and average latency
    - the model name and the prompt hash
  - an `@pytest.mark.llm` smoke test over 3 golden questions
- **Pass gate** — `make eval-agent` runs locally and writes a result file with every metric filled in.

### Step 31 — v2 release
- [ ] **Scope**
  - a README section on the agent: model choice, `AGENT_*` settings, and the safety model
  - `.env.example` and the compose files updated
  - CONTRACT §15 cleaned up
  - release `v2.0.0`, through a `Release-As: 2.0.0` commit footer for release-please
- **Pass gate** — A fresh clone, following only the README, runs Kontor v2.0.0 from the GHCR images, and the Ask tab answers a question end to end.
