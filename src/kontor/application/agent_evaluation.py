"""Scoring for the agent evaluation (CONTRACT §16.9): execution accuracy on a golden set."""

import time as clock
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal

from kontor.application.agent import AgentService
from kontor.domain.query import QueryResult
from kontor.ports.query_executor import QueryExecutor

CENT = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class GoldenItem:
    id: str
    question: str
    reference_sql: str
    ordered: bool = False


@dataclass(frozen=True, slots=True)
class Verdict:
    correct: bool
    reason: str | None = None  # why it is not correct


@dataclass(frozen=True, slots=True)
class ItemResult:
    id: str
    question: str
    status: str  # "answered" | "gave_up"
    correct: bool
    reason: str | None
    sql: str | None
    attempts: int
    latency_seconds: float
    empty_result: bool
    last_error: str | None


@dataclass(frozen=True, slots=True)
class AgentMetrics:
    questions: int
    execution_accuracy: float
    validity_rate: float
    give_up_rate: float
    empty_result_rate: float
    avg_attempts: float
    avg_latency_seconds: float


def evaluate_agent(
    service: AgentService,
    executor: QueryExecutor,
    items: Sequence[GoldenItem],
    *,
    timer: Callable[[], float] = clock.perf_counter,
    on_result: Callable[[ItemResult], None] = lambda _: None,
) -> list[ItemResult]:
    """Ask every golden question in a fresh conversation and score it against its reference.

    A failing reference query is a bug in the golden set and propagates. So do
    LLMUnavailableError and LLMTimeoutError: without the LLM there is nothing to measure.
    """
    results = []
    for item in items:
        expected = executor.execute(item.reference_sql)
        started = timer()
        _, answer = service.ask(item.question, None)
        latency = timer() - started
        if answer.status == "answered" and answer.result is not None:
            verdict = score(expected, answer.result, ordered=item.ordered)
            empty = is_empty(answer.result)
        else:
            verdict, empty = Verdict(False, "gave up"), False
        result = ItemResult(
            id=item.id,
            question=item.question,
            status=answer.status,
            correct=verdict.correct,
            reason=verdict.reason,
            sql=answer.sql,
            attempts=answer.attempts,
            latency_seconds=latency,
            empty_result=empty,
            last_error=answer.last_error,
        )
        on_result(result)
        results.append(result)
    return results


def score(expected: QueryResult, actual: QueryResult, *, ordered: bool) -> Verdict:
    """Compare results by value: column names ignored, numbers rounded to cents.

    Values within a row are compared regardless of column order, but the number of columns
    must match. Rows are a multiset unless `ordered`.
    """
    if len(expected.columns) != len(actual.columns):
        return Verdict(
            False, f"expected {len(expected.columns)} columns, got {len(actual.columns)}"
        )
    if len(expected.rows) != len(actual.rows):
        return Verdict(False, f"expected {len(expected.rows)} rows, got {len(actual.rows)}")
    want = [_row_key(row) for row in expected.rows]
    got = [_row_key(row) for row in actual.rows]
    if ordered:
        if want != got:
            return Verdict(False, "values or order differ")
    elif Counter(want) != Counter(got):
        return Verdict(False, "values differ")
    return Verdict(True)


def is_empty(result: QueryResult) -> bool:
    """No rows, or only NULLs: an aggregate over nothing (§16.6 notice in the UI)."""
    return all(value is None for row in result.rows for value in row)


def compute_metrics(results: Sequence[ItemResult]) -> AgentMetrics:
    total = len(results)
    if total == 0:
        return AgentMetrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    answered = [r for r in results if r.status == "answered"]
    return AgentMetrics(
        questions=total,
        execution_accuracy=sum(r.correct for r in results) / total,
        validity_rate=len(answered) / total,
        give_up_rate=(total - len(answered)) / total,
        empty_result_rate=sum(r.empty_result for r in answered) / total,
        avg_attempts=sum(r.attempts for r in results) / total,
        avg_latency_seconds=sum(r.latency_seconds for r in results) / total,
    )


def _row_key(row: Sequence[object]) -> tuple[str, ...]:
    return tuple(sorted(_normalize(value) for value in row))


def _normalize(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float | Decimal):
        return str(Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP))
    if isinstance(value, date | datetime | time):
        return value.isoformat()
    return str(value)
