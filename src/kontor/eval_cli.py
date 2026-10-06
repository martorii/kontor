"""Command line for the categorizer evaluation (CONTRACT §12).

python -m kontor.eval_cli export   # manual categorizations -> eval_export.jsonl
python -m kontor.eval_cli run      # labeled set -> eval_results/eval-<timestamp>.json
"""

import argparse
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kontor.adapters.db.uow import SqlUnitOfWork
from kontor.adapters.llm.lmstudio import LMStudioClient
from kontor.adapters.rules.yaml_source import YamlRulesSource
from kontor.application.evaluation import evaluate, export_labeled_set
from kontor.config import Settings
from kontor.domain.evaluation import LabeledExample
from kontor.logging import configure_logging

DEFAULT_EXPORT = Path("eval_export.jsonl")  # gitignored (eval_export*)
RESULTS_DIR = Path("eval_results")  # gitignored


def export(path: Path, settings: Settings) -> int:
    session_factory = sessionmaker(create_engine(settings.database_url))
    examples = export_labeled_set(lambda: SqlUnitOfWork(session_factory))
    with path.open("w", encoding="utf-8") as file:
        for example in examples:
            record = {**asdict(example), "amount": str(example.amount)}
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"exported {len(examples)} labeled transactions to {path}")
    return 0


def _read_examples(path: Path) -> list[LabeledExample]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [
        LabeledExample(**{**json.loads(line), "amount": Decimal(json.loads(line)["amount"])})
        for line in lines
        if line.strip()
    ]


def run(path: Path, threshold: float | None, settings: Settings) -> int:
    if not path.exists():
        print(f"{path} not found. Run `make eval-export` first.", file=sys.stderr)
        return 1
    examples = _read_examples(path)
    if not examples:
        print(f"{path} has no labeled transactions.", file=sys.stderr)
        return 1
    client = LMStudioClient(
        settings.llm_base_url,
        settings.llm_model,
        settings.llm_timeout_seconds,
        settings.llm_api_key,
    )
    if not client.is_healthy():
        print(f"LM Studio is not reachable at {settings.llm_base_url}.", file=sys.stderr)
        return 1
    rules = YamlRulesSource(Path(settings.rules_path)).load()
    used_threshold = settings.llm_confidence_threshold if threshold is None else threshold
    metrics, skipped = evaluate(client, examples, rules.categories, used_threshold)
    result = {
        "created_at": datetime.now(UTC).isoformat(),
        "model": client.model_name,
        "prompt_hash": client.prompt_hash,
        "rules_hash": rules.file_hash,
        "examples_in_file": len(examples),
        "skipped_unknown_category": skipped,
        "metrics": asdict(metrics),
        "note": (
            "The labeled set is made of manual categorizations, which are biased toward "
            "transactions the rules and the LLM got wrong or left open (CONTRACT §12.4)."
        ),
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    target = RESULTS_DIR / f"eval-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["metrics"], indent=2))
    print(f"result written to {target}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kontor.eval_cli")
    commands = parser.add_subparsers(dest="command", required=True)
    export_parser = commands.add_parser("export", help="export manual categorizations")
    export_parser.add_argument("--output", type=Path, default=DEFAULT_EXPORT)
    run_parser = commands.add_parser("run", help="evaluate the LLM on the labeled set")
    run_parser.add_argument("--input", type=Path, default=DEFAULT_EXPORT)
    run_parser.add_argument("--threshold", type=float, default=None)
    args = parser.parse_args(argv)

    settings = Settings()
    configure_logging(settings)
    if args.command == "export":
        return export(args.output, settings)
    return run(args.input, args.threshold, settings)


if __name__ == "__main__":
    raise SystemExit(main())
