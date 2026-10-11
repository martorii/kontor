# Kontor

Kontor is a local, single-user app for your bank transactions. It imports bank CSV exports, categorizes every transaction (your rules, then a local LLM, then you), stores everything in Postgres and shows spending reports. Since v2 you can also ask questions about your money in plain language: a local text-to-SQL agent answers them from your data. Nothing leaves your machine.

Supported bank format: **DKB checking account** CSV export. Every account is identified by the IBAN found in the file.

## What you need

- [Docker](https://docs.docker.com/get-docker/) with Compose, and `make`
- [LM Studio](https://lmstudio.ai/) on the same machine, for the categorizer and the agent
- a DKB CSV export (see [Import your first file](#6-import-your-first-file))

## Setup from a fresh clone

### 1. Clone

```bash
git clone https://github.com/martorii/kontor.git
cd kontor
```

### 2. LM Studio

Kontor uses two models, which can be the same one:

- **Categorizer**: needs JSON-schema structured output and token logprobs. Tested with `google_gemma-4-e2b-it`.
- **Agent** (the Ask page): `qwen/qwen3.5-9b` is recommended; see [Choosing the agent model](#choosing-the-agent-model).

1. Download the models in LM Studio and load them. Load the agent's model with a **context length of at least 10,000 tokens**: its prompt does not fit LM Studio's small default.
2. Start the local server (Developer tab) on port 1234.
3. On Linux, enable "Serve on Local Network" so the containers can reach it. Docker Desktop (macOS, Windows) needs nothing extra.
4. Note the model ids: `curl localhost:1234/v1/models` lists them.

LM Studio is optional for a first run: if it is not reachable, imports still succeed and the LLM step is skipped. Transactions the rules did not match stay uncategorized.

### 3. Configure `.env`

```bash
cp .env.example .env
```

Edit `.env`:

- `POSTGRES_PASSWORD`: pick your own password.
- `DATABASE_URL`: only used for runs on the host (tests, Alembic). Keep the password in sync.
- `CATEGORIZER_LLM_MODEL`: the model id from step 2.
- `CATEGORIZER_LLM_BASE_URL`: where the containers reach LM Studio. The example value, `http://host.docker.internal:1234/v1`, is right unless you changed LM Studio's port. The API refuses to start if either of these two is missing.
- `AGENT_LLM_MODEL` and `AGENT_LLM_BASE_URL`: the agent's model id from step 2, and where the containers reach LM Studio (the same URL as the categorizer's, normally). Both are required too. See [Asking questions](#asking-questions-the-agent) for the other agent settings.
- `API_PORT`, `UI_PORT`: change only if the defaults clash.

### 4. Create your rules

```bash
cp config/rules.example.yaml config/rules.yaml
```

`config/rules.yaml` holds your category tree and the rules that assign categories by counterparty, purpose or IBAN. It is gitignored. Kontor reads it and never writes to it. The comments at the top of the file explain the format. The API refuses to start if the file is missing or invalid.

### 5. Start Kontor

```bash
make deploy
```

This pulls the pinned release images from GHCR and starts Postgres, runs the migrations, and starts the API and the UI. Check that everything is healthy:

```bash
docker compose ps
```

The UI is at http://localhost:8501 and the API at http://localhost:8000.

### 6. Import your first file

1. Export your transactions from DKB as CSV (checking account).
2. Open the **Upload** page and upload the file.
3. The import runs your rules, then the LLM on what is left, and reports how many transactions are new, duplicates, rule-matched, LLM-matched and uncategorized.

Uploading the same file twice is safe: duplicates are detected and skipped. A new IBAN creates an account automatically; edit its name and details on the **Accounts** page.

## Using Kontor

| Page | Purpose |
|---|---|
| Monthly overview | Spending per category for a month; open a category to see its transactions and change a category |
| Year comparison | A year against the previous one, per category |
| Ask | Questions about your money in plain language, answered by the agent; see below |
| Top merchants | Biggest merchants for a date range and one or more accounts |
| Review | Uncategorized transactions with the LLM's suggestions; assign a category in one click; re-run the rules with a dry-run preview |
| Transaction explorer | Filter all transactions and relabel them |
| Re-run LLM | Ask the LLM again for every uncategorized transaction, for example after LM Studio was offline |
| Upload, Import history, Accounts | Import files and manage accounts |

Manual categorizations always win: neither the rules nor the LLM overwrite them. After you edit `rules.yaml`, use **Review → Re-run rules** to apply the changes.

## Asking questions (the agent)

The **Ask** page answers questions such as "How much did I spend on groceries last month?" or "Which five merchants did I spend the most at this year?". The agent writes a SQL query, runs it read-only, and answers with a short summary, the result table, a chart when one helps, and the query itself. Follow-up questions ("and the month before?") keep the context of the conversation.

Under each answer, **Details** lists every attempt: the plan the model wrote, its SQL, and the error or the number of rows. When a query matched no data, the page says so: usually a filter on a value that does not exist.

### Choosing the agent model

Measured with `make eval-agent` on the golden set (27 questions, synthetic data):

| Model | Correct answers | Time per question |
|---|---|---|
| `qwen/qwen3.5-9b` (recommended) | 85% | about 19 s |
| `google_gemma-4-e2b-it` | 70% | about 5 s |
| `arctic-text2sql-r1-7b` | 26% | about 14 s |

The agent's prompt needs a context length of at least 10,000 tokens. Thinking is turned off by default, because thinking models return empty structured output in LM Studio.

### Agent settings

| Setting | Default | Meaning |
|---|---|---|
| `AGENT_LLM_BASE_URL` | (required) | Where the API reaches LM Studio |
| `AGENT_LLM_MODEL` | (required) | The model id |
| `AGENT_LLM_API_KEY` | `lm-studio` | API key sent to LM Studio |
| `AGENT_LLM_TIMEOUT_SECONDS` | `120` | Timeout of one model call |
| `AGENT_LLM_REASONING_EFFORT` | `none` | Thinking for reasoning models: `none`, `minimal`, `low`, `medium`, `high` |
| `AGENT_MAX_RETRIES` | `2` | Retries after a rejected or failing query |
| `AGENT_SUMMARY_ROWS` | `50` | Rows the model sees when it writes the answer |
| `AGENT_MAX_TURNS` | `10` | Turns kept per conversation |
| `AGENT_CONVERSATION_TTL_MINUTES` | `60` | Idle time before a conversation is forgotten |
| `AGENT_STATEMENT_TIMEOUT_SECONDS` | `10` | Postgres timeout of one query |
| `AGENT_MAX_ROWS` | `500` | Rows returned to the page; larger results are cut off and marked |

### What the agent can and cannot do

- **It only reads.** Queries run in a read-only transaction as a database role that can `SELECT` from four relations only: `v_flows`, `transactions`, `accounts` and `categories`. A request to change data cannot change anything.
- **Every query is checked before it runs.** It must be a single `SELECT` over those relations, with no functions that have side effects. A rejected or failing query goes back to the model with the error, at most twice.
- **Queries are bounded** by the statement timeout and the row cap above.
- **Conversations live in the API's memory**, never in the database. A restart forgets them.
- **It can be wrong.** Check the SQL under Details when an answer matters. Sums of money over transfers, savings and refunds are where it errs most.

## Updating and rolling back

```bash
make deploy                 # pull the pinned images and restart
make deploy-main-locally      # git pull main, then build from source and restart
make rollback TAG=vX.Y.Z    # pin a previous release
```

Your data lives in the Docker volume `kontor_pgdata` and survives redeploys.

## Your data

- There is **no backup service**. Recovery means re-importing your CSV exports, which restores everything except manual categorizations.
- `make reset-db` deletes **all** data (it asks for confirmation).
- Never commit bank exports, `config/rules.yaml`, `.env` or eval exports. They are gitignored, and gitleaks runs in CI.

## Evaluating the categorizer

`make eval-export` writes your manual categorizations to `eval_export.jsonl`; `make eval` runs them through the LLM and writes a JSON result file to `eval_results/`. Both are gitignored. Run them on the host with `DATABASE_URL` and `CATEGORIZER_LLM_BASE_URL=http://localhost:1234/v1` pointing at reachable services. The compose Postgres is not published, so you can also run the export inside the container: `docker compose exec api python -m kontor.eval_cli export`.

## Evaluating the agent

`make eval-agent` asks the agent every question in `tests/agent_eval/golden.yaml` and compares each result with the result of the question's reference SQL. It runs on synthetic data in a throwaway Postgres container, which it removes afterwards, so your real data is never touched. It needs Docker and LM Studio with your agent model. On the host, point it at LM Studio on localhost:

```bash
AGENT_LLM_BASE_URL=http://localhost:1234/v1 make eval-agent
```

It prints one line per question and writes `eval_results/agent-<timestamp>.json` (gitignored) with the metrics and, for every question, the SQL, the attempts and why it failed. The metrics are:

- **execution accuracy**: the share of questions whose result matches the reference result
- **validity rate** and **give-up rate**: the share of questions that got a working query, and the share that did not
- **empty-result rate**: the share of questions answered with no data, usually a filter on a value that does not exist
- **average attempts** and **average latency**

The file also records the model name and the prompt hash. Compare runs before and after you change the model or the prompt.

## Development

Prerequisites: [uv](https://docs.astral.sh/uv/) and [gitleaks](https://github.com/gitleaks/gitleaks) (`brew install gitleaks`).

```bash
uv sync
uv run pre-commit install
make lint typecheck test
```

Build and run the stack from source instead of the release images:

```bash
docker compose up -d --build --wait
```

Design decisions are in [CONTRACT.md](CONTRACT.md); the order of work is in [PLAN.md](PLAN.md).
