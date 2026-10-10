#!/usr/bin/env bash
# Run the agent evaluation against a throwaway Postgres (CONTRACT §16.9).
# The container is removed afterwards, whatever happens. Your real database is never touched.
set -euo pipefail

name="kontor-agent-eval-$$"
port="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"

docker run --rm -d --name "$name" \
  -e POSTGRES_USER=eval -e POSTGRES_PASSWORD=eval -e POSTGRES_DB=eval \
  -p "127.0.0.1:${port}:5432" postgres:18-alpine >/dev/null
trap 'docker stop "$name" >/dev/null' EXIT

for _ in $(seq 60); do
  # pg_isready can pass during the image's init restart; a real query is the reliable check.
  if docker exec "$name" psql -U eval -d eval -c 'SELECT 1' >/dev/null 2>&1; then break; fi
  sleep 1
done

DATABASE_URL="postgresql+psycopg://eval:eval@127.0.0.1:${port}/eval" \
  uv run python -m kontor.agent_eval_cli "$@"
