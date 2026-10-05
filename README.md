# kontor

## Development

Prerequisites: [uv](https://docs.astral.sh/uv/) and [gitleaks](https://github.com/gitleaks/gitleaks) (`brew install gitleaks`).

```bash
uv sync
uv run pre-commit install
make lint typecheck test
```

## Running the stack

```bash
cp .env.example .env     # then edit the placeholder values
docker compose up -d --build --wait
```

Check each service on its own:

```bash
docker compose ps                                              # health of every service
curl localhost:8000/health                                     # API only (does not check the database yet)
docker compose exec postgres pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"   # Postgres only
```

The UI is at http://localhost:8501 (`UI_PORT` in `.env`). Change `API_PORT` in `.env` if port 8000 is taken. Postgres data lives in the named volume `kontor_pgdata`; `docker compose down -v` deletes it.
