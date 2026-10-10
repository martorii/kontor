# Kontor

Kontor is a local, single-user app for your bank transactions. It imports bank CSV exports, categorizes every transaction (your rules, then a local LLM, then you), stores everything in Postgres and shows spending reports. Nothing leaves your machine.

Supported bank format: **DKB checking account** CSV export. Every account is identified by the IBAN found in the file.

## What you need

- [Docker](https://docs.docker.com/get-docker/) with Compose, and `make`
- [LM Studio](https://lmstudio.ai/) on the same machine, for the LLM step
- a DKB CSV export (see [Import your first file](#5-import-your-first-file))

## Setup from a fresh clone

### 1. Clone

```bash
git clone https://github.com/martorii/kontor.git
cd kontor
```

### 2. LM Studio

1. Download a model in LM Studio and load it. Kontor needs JSON-schema structured output and token logprobs; it was tested with `google_gemma-4-e2b-it`.
2. Start the local server (Developer tab) on port 1234.
3. On Linux, enable "Serve on Local Network" so the containers can reach it. Docker Desktop (macOS, Windows) needs nothing extra.
4. Note the model id: `curl localhost:1234/v1/models` lists it.

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
- `AGENT_LLM_MODEL` and `AGENT_LLM_BASE_URL`: the model the text-to-SQL agent uses, and where it is served. Like the categorizer's, both are required. A model tuned for code writes better SQL than a small chat model; it can be a different model in the same LM Studio.
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
| Top merchants | Biggest merchants for a year or a month |
| Review | Uncategorized transactions with the LLM's suggestions; assign a category in one click; re-run the rules with a dry-run preview |
| Transaction explorer | Filter all transactions and relabel them |
| Upload, Import history, Accounts | Import files and manage accounts |

Manual categorizations always win: neither the rules nor the LLM overwrite them. After you edit `rules.yaml`, use **Review → Re-run rules** to apply the changes.

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
