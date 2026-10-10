"""Command line for the agent evaluation (CONTRACT §16.9). Run it through `make eval-agent`.

python -m kontor.agent_eval_cli [--golden tests/agent_eval/golden.yaml]

It migrates and seeds the database at DATABASE_URL with synthetic data, so it refuses any
database that already has tables. `make eval-agent` starts a throwaway Postgres for it.
"""

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any  # Any: YAML documents are untyped by nature

import yaml
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

from kontor.adapters.db.query_executor import PostgresQueryExecutor
from kontor.adapters.db.schema_introspector import PostgresSchemaIntrospector
from kontor.adapters.llm.lmstudio_agent import LMStudioAgentLLM
from kontor.agent_eval_seed import seed
from kontor.application.agent import AgentService
from kontor.application.agent_context import load_notes
from kontor.application.agent_conversations import ConversationStore
from kontor.application.agent_evaluation import (
    GoldenItem,
    ItemResult,
    compute_metrics,
    evaluate_agent,
)
from kontor.config import ConfigurationError, Settings
from kontor.domain.errors import LLMTimeoutError, LLMUnavailableError
from kontor.logging import configure_logging

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GOLDEN = ROOT / "tests" / "agent_eval" / "golden.yaml"
RESULTS_DIR = Path("eval_results")  # gitignored


def load_golden(path: Path) -> list[GoldenItem]:
    document: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    items = [
        GoldenItem(
            id=str(raw["id"]),
            question=str(raw["question"]),
            reference_sql=str(raw["reference_sql"]).strip(),
            ordered=bool(raw.get("ordered", False)),
        )
        for raw in document["items"]
    ]
    ids = [item.id for item in items]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"duplicate golden ids: {', '.join(duplicates)}")
    return items


def has_tables(engine: Engine) -> bool:
    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'public'")
        ).scalar_one()
    return bool(count)


def run(golden_path: Path, settings: Settings) -> int:
    try:
        settings.require_agent_llm()
    except ConfigurationError as exc:
        print(exc, file=sys.stderr)
        return 1
    items = load_golden(golden_path)
    engine = create_engine(settings.database_url)
    if has_tables(engine):
        print(
            "The database at DATABASE_URL already has tables. The agent eval only runs on an "
            "empty scratch database; use `make eval-agent`.",
            file=sys.stderr,
        )
        return 1
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    today = date.today()
    transactions = seed(engine, today)

    llm = LMStudioAgentLLM(
        settings.agent_llm_base_url,
        settings.agent_llm_model,
        settings.agent_llm_timeout_seconds,
        settings.agent_llm_api_key,
    )
    executor = PostgresQueryExecutor(
        engine, settings.agent_statement_timeout_seconds, settings.agent_max_rows
    )
    service = AgentService(
        llm,
        executor,
        PostgresSchemaIntrospector(engine).introspect(),
        load_notes(),
        ConversationStore(len(items), timedelta(hours=1)),
        max_retries=settings.agent_max_retries,
        summary_rows=settings.agent_summary_rows,
    )
    print(f"{len(items)} questions, {transactions} synthetic transactions, model {llm.model_name}")
    try:
        results = evaluate_agent(service, executor, items, on_result=_print_result)
    except (LLMUnavailableError, LLMTimeoutError) as exc:
        print(f"LM Studio failed at {settings.agent_llm_base_url}: {exc}", file=sys.stderr)
        return 1

    metrics = compute_metrics(results)
    result = {
        "created_at": datetime.now(UTC).isoformat(),
        "model": llm.model_name,
        "prompt_hash": service.prompt_hash,
        "golden_hash": hashlib.sha256(golden_path.read_bytes()).hexdigest(),
        "seed_date": today.isoformat(),
        "seed_transactions": transactions,
        "metrics": asdict(metrics),
        "items": [asdict(item) for item in results],
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    target = RESULTS_DIR / f"agent-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["metrics"], indent=2))
    print(f"result written to {target}")
    return 0


def _print_result(item: ItemResult) -> None:
    mark = "ok  " if item.correct else "FAIL"
    detail = "" if item.correct else f" ({item.reason})"
    print(f"{mark} {item.id}: {item.attempts} attempt(s), {item.latency_seconds:.1f}s{detail}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kontor.agent_eval_cli")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    args = parser.parse_args(argv)
    settings = Settings()
    # WARNING: the agent's info lines would drown the per-question summary.
    configure_logging(settings.model_copy(update={"log_level": "WARNING"}))
    return run(args.golden, settings)


if __name__ == "__main__":
    raise SystemExit(main())
