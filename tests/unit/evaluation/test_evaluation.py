import json
from decimal import Decimal
from pathlib import Path

import pytest

from kontor.adapters.llm.fake import FakeLLMClient
from kontor.adapters.llm.lmstudio import PROMPT_HASH, _prompt_hash
from kontor.application.evaluation import evaluate
from kontor.config import Settings
from kontor.domain.evaluation import EvalCase, LabeledExample, compute_metrics
from kontor.domain.llm import LLMSuggestion
from kontor.domain.rules import CategoryDef
from kontor.eval_cli import _read_examples, run

CATEGORIES = (
    CategoryDef("food", "Food", None, "expense"),
    CategoryDef("food.groceries", "Groceries", "food", None),
    CategoryDef("food.restaurants", "Restaurants", "food", None),
    CategoryDef("housing", "Housing", None, "expense"),
    CategoryDef("housing.rent", "Rent", "housing", None),
)
PARENTS = {"food.groceries": "food", "food.restaurants": "food", "housing.rent": "housing"}


def example(counterparty: str, category: str) -> LabeledExample:
    return LabeledExample(counterparty, "", Decimal("-10.00"), "EUR", category)


def test_metrics_cover_every_contract_field() -> None:
    cases = [
        EvalCase("food.groceries", "food.groceries", 0.95, 1.0),  # right, covered
        EvalCase("food.groceries", "food.restaurants", 0.90, 2.0),  # right parent, covered
        EvalCase("housing.rent", "food.groceries", 0.40, 3.0),  # wrong, not covered
        EvalCase("housing.rent", None, None, 9.0),  # failed call
    ]

    metrics = compute_metrics(cases, PARENTS, threshold=0.8)

    assert (metrics.total, metrics.answered, metrics.failed) == (4, 3, 1)
    assert metrics.subcategory_accuracy == pytest.approx(1 / 3)
    assert metrics.top_level_accuracy == pytest.approx(2 / 3)
    assert metrics.coverage == pytest.approx(2 / 3)
    assert metrics.covered_accuracy == pytest.approx(1 / 2)
    assert metrics.average_latency_seconds == pytest.approx(2.0)


def test_metrics_are_none_without_a_denominator() -> None:
    metrics = compute_metrics([EvalCase("housing.rent", None, None, 1.0)], PARENTS, 0.8)

    assert metrics.answered == 0
    assert metrics.subcategory_accuracy is None
    assert metrics.coverage is None
    assert metrics.covered_accuracy is None
    assert metrics.average_latency_seconds is None


def test_evaluate_runs_each_example_and_skips_categories_that_no_longer_exist() -> None:
    client = FakeLLMClient(
        answers={
            "REWE": LLMSuggestion("food.groceries", 0.99),
            "LANDLORD": LLMSuggestion("food.restaurants", 0.50),
        }
    )
    examples = [
        example("REWE", "food.groceries"),
        example("LANDLORD", "housing.rent"),
        example("OLD", "deleted.category"),
        example("UNSCRIPTED", "food.groceries"),  # the fake raises: a failed call
    ]

    metrics, skipped = evaluate(client, examples, CATEGORIES, 0.8)

    assert skipped == 1
    assert (metrics.total, metrics.answered, metrics.failed) == (3, 2, 1)
    assert metrics.subcategory_accuracy == 0.5
    assert metrics.coverage == 0.5
    assert metrics.covered_accuracy == 1.0


def test_prompt_hash_is_stable() -> None:
    assert _prompt_hash() == PROMPT_HASH
    assert len(PROMPT_HASH) == 64


def test_read_examples_parses_the_export_format(tmp_path: Path) -> None:
    path = tmp_path / "export.jsonl"
    record = {
        "counterparty": "REWE",
        "purpose": "groceries",
        "amount": "-12.30",
        "currency": "EUR",
        "category_slug": "food.groceries",
    }
    path.write_text(json.dumps(record) + "\n\n", encoding="utf-8")

    assert _read_examples(path) == [
        LabeledExample("REWE", "groceries", Decimal("-12.30"), "EUR", "food.groceries")
    ]


def test_run_without_an_export_fails_with_a_hint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(tmp_path / "missing.jsonl", None, Settings()) == 1
    assert "make eval-export" in capsys.readouterr().err


def test_run_without_categorizer_llm_fails_with_the_variable_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    export = tmp_path / "export.jsonl"
    record = {
        "counterparty": "Example Shop",
        "purpose": "groceries",
        "amount": "-12.30",
        "currency": "EUR",
        "category_slug": "food.groceries",
    }
    export.write_text(json.dumps(record) + "\n", encoding="utf-8")

    assert run(export, None, Settings(_env_file=None)) == 1  # type: ignore[call-arg]
    assert "CATEGORIZER_LLM_BASE_URL" in capsys.readouterr().err
