from datetime import date, timedelta
from decimal import Decimal
from itertools import count
from pathlib import Path

import pytest

from kontor.adapters.llm.fake_agent import FakeAgentLLM
from kontor.agent_eval_cli import DEFAULT_GOLDEN, load_golden
from kontor.application.agent import AgentService
from kontor.application.agent_conversations import ConversationStore
from kontor.application.agent_evaluation import (
    GoldenItem,
    ItemResult,
    compute_metrics,
    evaluate_agent,
    is_empty,
    score,
)
from kontor.domain.agent import NO_CHART, Summary
from kontor.domain.query import QueryResult
from kontor.domain.schema import Column, Relation, SchemaInfo


def result(*rows: tuple[object, ...], columns: int | None = None) -> QueryResult:
    width = columns if columns is not None else (len(rows[0]) if rows else 1)
    return QueryResult(tuple(f"c{i}" for i in range(width)), rows, truncated=False)


def test_equal_results_are_correct() -> None:
    assert score(result(("a", 1)), result(("a", 1)), ordered=False).correct


def test_column_names_are_ignored() -> None:
    expected = QueryResult(("merchant", "spent"), (("A", Decimal("1.00")),), truncated=False)
    actual = QueryResult(("name", "total"), (("A", Decimal("1.00")),), truncated=False)

    assert score(expected, actual, ordered=False).correct


def test_numbers_are_compared_to_the_cent() -> None:
    expected = result((Decimal("12.3456"),))

    assert score(expected, result((Decimal("12.35"),)), ordered=False).correct
    assert score(expected, result((12.345,)), ordered=False).correct
    assert not score(expected, result((Decimal("12.34"),)), ordered=False).correct


def test_int_and_decimal_are_the_same_number() -> None:
    assert score(result((10,)), result((Decimal("10.0"),)), ordered=False).correct


def test_column_order_within_a_row_does_not_matter() -> None:
    assert score(result(("A", Decimal("5"))), result((Decimal("5"), "A")), ordered=False).correct


def test_column_count_must_match() -> None:
    verdict = score(result(("A", 1)), result(("A", 1, 2)), ordered=False)

    assert not verdict.correct
    assert verdict.reason == "expected 2 columns, got 3"


def test_row_count_must_match() -> None:
    verdict = score(result(("A",), ("B",)), result(("A",)), ordered=False)

    assert verdict.reason == "expected 2 rows, got 1"


def test_unordered_rows_are_a_multiset() -> None:
    expected = result(("A",), ("B",), ("B",))

    assert score(expected, result(("B",), ("A",), ("B",)), ordered=False).correct
    assert not score(expected, result(("A",), ("A",), ("B",)), ordered=False).correct


def test_ordered_rows_must_keep_their_order() -> None:
    verdict = score(result(("A",), ("B",)), result(("B",), ("A",)), ordered=True)

    assert not verdict.correct
    assert verdict.reason == "values or order differ"


def test_nulls_dates_and_booleans() -> None:
    row = (None, date(2026, 1, 15), True)

    assert score(result(row), result(row), ordered=False).correct
    assert not score(result(row), result((None, date(2026, 1, 16), True)), ordered=False).correct


def test_is_empty() -> None:
    assert is_empty(result(columns=1))
    assert is_empty(result((None,)))
    assert not is_empty(result((None,), (Decimal("0"),)))


def item_result(**overrides: object) -> ItemResult:
    fields: dict[str, object] = {
        "id": "x",
        "question": "q",
        "status": "answered",
        "correct": True,
        "reason": None,
        "sql": "SELECT 1",
        "attempts": 1,
        "latency_seconds": 2.0,
        "empty_result": False,
        "last_error": None,
    }
    return ItemResult(**(fields | overrides))  # type: ignore[arg-type]


def test_metrics() -> None:
    metrics = compute_metrics(
        [
            item_result(),
            item_result(correct=False, empty_result=True, attempts=2, latency_seconds=4.0),
            item_result(status="gave_up", correct=False, attempts=3, latency_seconds=6.0),
            item_result(correct=False),
        ]
    )

    assert metrics.questions == 4
    assert metrics.execution_accuracy == 0.25
    assert metrics.validity_rate == 0.75
    assert metrics.give_up_rate == 0.25
    assert metrics.empty_result_rate == 0.25
    assert metrics.avg_attempts == 7 / 4
    assert metrics.avg_latency_seconds == 3.5


def test_metrics_of_nothing() -> None:
    assert compute_metrics([]).questions == 0


class FakeExecutor:
    def __init__(self, results: dict[str, QueryResult]) -> None:
        self.results = results

    def execute(self, sql: str) -> QueryResult:
        return self.results[sql]


SCHEMA = SchemaInfo((Relation("v_flows", "view", (Column("amount", "numeric(12,2)"),)),), ())


def test_evaluate_agent_scores_each_question_in_a_fresh_conversation() -> None:
    reference = "SELECT SUM(amount) FROM v_flows"
    executor = FakeExecutor(
        {
            reference: result((Decimal("10.00"),)),
            "SELECT 10 FROM v_flows": result((10,)),
            "SELECT NULL FROM v_flows": result((None,)),
        }
    )
    llm = FakeAgentLLM(
        sql=["SELECT 10 FROM v_flows", "SELECT NULL FROM v_flows", "DROP VIEW v_flows"],
        summaries=[Summary("ok", NO_CHART), Summary("ok", NO_CHART)],
    )
    service = AgentService(
        llm,
        executor,
        SCHEMA,
        "notes",
        ConversationStore(10, timedelta(hours=1)),
        max_retries=0,
        summary_rows=10,
    )
    items = [GoldenItem(name, "q", reference) for name in ("right", "empty", "gave-up")]
    ticks = count()

    results = evaluate_agent(service, executor, items, timer=lambda: float(next(ticks)))

    right, empty, gave_up = results
    assert (right.correct, right.empty_result, right.latency_seconds) == (True, False, 1.0)
    assert (empty.correct, empty.empty_result, empty.reason) == (False, True, "values differ")
    assert (gave_up.status, gave_up.correct, gave_up.reason) == ("gave_up", False, "gave up")
    assert all(call.history == () for call in llm.sql_calls)


def test_the_golden_set_loads_with_at_least_25_unique_items() -> None:
    items = load_golden(DEFAULT_GOLDEN)

    assert len(items) >= 25
    assert len({item.id for item in items}) == len(items)
    assert all(item.reference_sql.upper().startswith("SELECT") for item in items)


def test_duplicate_golden_ids_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "golden.yaml"
    path.write_text(
        "items:\n"
        "  - {id: a, question: q, reference_sql: SELECT 1}\n"
        "  - {id: a, question: q, reference_sql: SELECT 2}\n"
    )

    with pytest.raises(ValueError, match="duplicate golden ids: a"):
        load_golden(path)
