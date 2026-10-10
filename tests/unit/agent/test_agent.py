from datetime import timedelta
from decimal import Decimal

import pytest

from kontor.adapters.llm.fake_agent import FakeAgentLLM
from kontor.application.agent import (
    FALLBACK_ANSWER,
    GAVE_UP_ANSWER,
    AgentService,
    check_chart,
)
from kontor.application.agent_conversations import ConversationStore
from kontor.domain.agent import NO_CHART, ChartSpec, Summary
from kontor.domain.errors import (
    LLMInvalidOutputError,
    LLMUnavailableError,
    QueryExecutionError,
    QueryTimeoutError,
)
from kontor.domain.query import QueryResult
from kontor.domain.schema import Column, Relation, SchemaInfo

SCHEMA = SchemaInfo(
    relations=(
        Relation(
            "v_flows",
            "view",
            (Column("month", "integer"), Column("amount", "numeric(12,2)")),
        ),
    ),
    foreign_keys=(),
)

GOOD_SQL = "SELECT month, SUM(-amount) AS spent FROM v_flows GROUP BY month"
MONTHLY = QueryResult(
    columns=("month", "spent"),
    rows=((1, Decimal("120.50")), (2, Decimal("98.00"))),
    truncated=False,
)
BAR = ChartSpec("bar", "month", "spent")


class FakeExecutor:
    """Returns or raises the scripted outcomes in order and records the SQL it receives."""

    def __init__(self, *outcomes: QueryResult | Exception) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[str] = []

    def execute(self, sql: str) -> QueryResult:
        self.calls.append(sql)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def make_service(
    llm: FakeAgentLLM,
    executor: FakeExecutor,
    *,
    store: ConversationStore | None = None,
    max_retries: int = 2,
    summary_rows: int = 50,
) -> AgentService:
    return AgentService(
        llm,
        executor,
        SCHEMA,
        "NOTES",
        store or ConversationStore(max_turns=10, ttl=timedelta(minutes=60)),
        max_retries=max_retries,
        summary_rows=summary_rows,
    )


def test_happy_path_answers_with_sql_rows_and_chart() -> None:
    llm = FakeAgentLLM(sql=[GOOD_SQL], summaries=[Summary("You spent 218.50.", BAR)])
    executor = FakeExecutor(MONTHLY)

    _, answer = make_service(llm, executor).ask("How much per month?", None)

    assert answer.status == "answered"
    assert answer.answer == "You spent 218.50."
    assert answer.sql == GOOD_SQL
    assert answer.result == MONTHLY
    assert answer.chart == BAR
    assert answer.attempts == 1
    assert answer.last_error is None
    assert executor.calls == [GOOD_SQL]


def test_context_holds_the_notes_and_the_schema() -> None:
    llm = FakeAgentLLM(sql=[GOOD_SQL], summaries=[Summary("ok", NO_CHART)])

    make_service(llm, FakeExecutor(MONTHLY)).ask("q", None)

    context = llm.sql_calls[0].context
    assert context.startswith("NOTES")
    assert "view v_flows" in context
    assert "amount numeric(12,2)" in context


def test_validator_rejection_is_retried_with_the_error() -> None:
    llm = FakeAgentLLM(sql=["DELETE FROM v_flows", GOOD_SQL], summaries=[Summary("ok", NO_CHART)])
    executor = FakeExecutor(MONTHLY)

    _, answer = make_service(llm, executor).ask("q", None)

    assert answer.status == "answered"
    assert answer.attempts == 2
    assert executor.calls == [GOOD_SQL]
    retry = llm.sql_calls[1].failed_attempts
    assert len(retry) == 1
    assert retry[0].sql == "DELETE FROM v_flows"
    assert "rejected by the validator" in retry[0].error
    assert "DELETE" in retry[0].error


def test_execution_error_is_retried() -> None:
    llm = FakeAgentLLM(
        sql=["SELECT nope FROM v_flows", GOOD_SQL], summaries=[Summary("ok", NO_CHART)]
    )
    executor = FakeExecutor(QueryExecutionError('column "nope" does not exist'), MONTHLY)

    _, answer = make_service(llm, executor).ask("q", None)

    assert answer.status == "answered"
    assert answer.attempts == 2
    assert 'column "nope" does not exist' in llm.sql_calls[1].failed_attempts[0].error


def test_timeout_is_retried() -> None:
    llm = FakeAgentLLM(sql=[GOOD_SQL, GOOD_SQL], summaries=[Summary("ok", NO_CHART)])
    executor = FakeExecutor(QueryTimeoutError("canceling statement"), MONTHLY)

    _, answer = make_service(llm, executor).ask("q", None)

    assert answer.attempts == 2
    assert "timed out" in llm.sql_calls[1].failed_attempts[0].error


def test_gives_up_after_the_retries_and_never_runs_unvalidated_sql() -> None:
    llm = FakeAgentLLM(sql=["DROP VIEW v_flows", "SELECT * FROM secrets", "UPDATE x SET y = 1"])
    executor = FakeExecutor()

    _, answer = make_service(llm, executor).ask("q", None)

    assert answer.status == "gave_up"
    assert answer.answer == GAVE_UP_ANSWER
    assert answer.attempts == 3
    assert answer.sql == "UPDATE x SET y = 1"
    assert answer.last_error is not None and "UPDATE" in answer.last_error
    assert answer.result is None
    assert answer.chart == NO_CHART
    assert executor.calls == []
    assert llm.summary_calls == []


def test_max_retries_zero_means_one_attempt() -> None:
    llm = FakeAgentLLM(sql=["DROP VIEW v_flows"])

    _, answer = make_service(llm, FakeExecutor(), max_retries=0).ask("q", None)

    assert answer.status == "gave_up"
    assert answer.attempts == 1


def test_unusable_sql_output_counts_as_an_attempt() -> None:
    llm = FakeAgentLLM(
        sql=[LLMInvalidOutputError("not JSON"), GOOD_SQL], summaries=[Summary("ok", NO_CHART)]
    )

    _, answer = make_service(llm, FakeExecutor(MONTHLY)).ask("q", None)

    assert answer.attempts == 2
    failed = llm.sql_calls[1].failed_attempts[0]
    assert failed.sql is None
    assert "unusable model output" in failed.error


def test_unusable_summary_falls_back_without_losing_the_result() -> None:
    llm = FakeAgentLLM(sql=[GOOD_SQL], summaries=[LLMInvalidOutputError("not JSON")])

    _, answer = make_service(llm, FakeExecutor(MONTHLY)).ask("q", None)

    assert answer.status == "answered"
    assert answer.answer == FALLBACK_ANSWER
    assert answer.chart == NO_CHART
    assert answer.result == MONTHLY


def test_invalid_chart_from_the_model_becomes_none() -> None:
    llm = FakeAgentLLM(sql=[GOOD_SQL], summaries=[Summary("ok", ChartSpec("bar", "x", "y"))])

    _, answer = make_service(llm, FakeExecutor(MONTHLY)).ask("q", None)

    assert answer.chart == NO_CHART


@pytest.mark.parametrize(
    ("chart", "expected"),
    [
        (BAR, BAR),
        (ChartSpec("line", "month", "spent"), ChartSpec("line", "month", "spent")),
        (ChartSpec("none"), NO_CHART),
        (ChartSpec("bar", "unknown", "spent"), NO_CHART),
        (ChartSpec("bar", "month", "unknown"), NO_CHART),
        (ChartSpec("bar", None, "spent"), NO_CHART),
        (ChartSpec("bar", "spent", "month"), ChartSpec("bar", "spent", "month")),
    ],
)
def test_check_chart(chart: ChartSpec, expected: ChartSpec) -> None:
    assert check_chart(chart, MONTHLY) == expected


def test_check_chart_needs_a_numeric_y() -> None:
    result = QueryResult(("merchant", "note"), (("A", "x"), ("B", None)), truncated=False)

    assert check_chart(ChartSpec("bar", "merchant", "note"), result) == NO_CHART


def test_check_chart_ignores_nulls_but_needs_some_numbers() -> None:
    some = QueryResult(("m", "v"), (("A", None), ("B", Decimal("1"))), truncated=False)
    none = QueryResult(("m", "v"), (("A", None),), truncated=False)
    flags = QueryResult(("m", "v"), (("A", True),), truncated=False)

    assert check_chart(ChartSpec("bar", "m", "v"), some) == ChartSpec("bar", "m", "v")
    assert check_chart(ChartSpec("bar", "m", "v"), none) == NO_CHART
    assert check_chart(ChartSpec("bar", "m", "v"), flags) == NO_CHART


def test_summary_sees_at_most_summary_rows_and_the_truncation() -> None:
    rows = tuple((i, Decimal(i)) for i in range(10))
    llm = FakeAgentLLM(sql=[GOOD_SQL], summaries=[Summary("ok", NO_CHART)])
    executor = FakeExecutor(QueryResult(("month", "spent"), rows, truncated=False))

    _, answer = make_service(llm, executor, summary_rows=3).ask("q", None)

    call = llm.summary_calls[0]
    assert call.rows == rows[:3]
    assert call.truncated is True
    assert answer.result is not None and answer.result.rows == rows


def test_summary_is_told_when_the_executor_truncated() -> None:
    llm = FakeAgentLLM(sql=[GOOD_SQL], summaries=[Summary("ok", NO_CHART)])
    truncated = QueryResult(MONTHLY.columns, MONTHLY.rows, truncated=True)

    make_service(llm, FakeExecutor(truncated)).ask("q", None)

    assert llm.summary_calls[0].truncated is True


def test_llm_unavailable_propagates() -> None:
    llm = FakeAgentLLM(sql=[LLMUnavailableError("down")])

    with pytest.raises(LLMUnavailableError):
        make_service(llm, FakeExecutor()).ask("q", None)


def test_follow_up_sees_the_previous_turn_but_not_its_rows() -> None:
    llm = FakeAgentLLM(
        sql=[GOOD_SQL, GOOD_SQL],
        summaries=[Summary("January: 120.50.", NO_CHART), Summary("ok", NO_CHART)],
    )
    service = make_service(llm, FakeExecutor(MONTHLY, MONTHLY))

    conversation_id, _ = service.ask("Spending in January?", None)
    same_id, _ = service.ask("And February?", conversation_id)

    assert same_id == conversation_id
    assert llm.sql_calls[0].history == ()
    (turn,) = llm.sql_calls[1].history
    assert turn.question == "Spending in January?"
    assert turn.sql == GOOD_SQL
    assert turn.answer == "January: 120.50."


def test_gave_up_turns_are_kept_for_follow_ups() -> None:
    llm = FakeAgentLLM(sql=["DROP VIEW v_flows", GOOD_SQL], summaries=[Summary("ok", NO_CHART)])
    service = make_service(llm, FakeExecutor(MONTHLY), max_retries=0)

    conversation_id, first = service.ask("q1", None)
    service.ask("why not?", conversation_id)

    assert first.status == "gave_up"
    assert llm.sql_calls[1].history[0].answer == GAVE_UP_ANSWER


def test_unknown_conversation_starts_fresh() -> None:
    llm = FakeAgentLLM(sql=[GOOD_SQL], summaries=[Summary("ok", NO_CHART)])

    conversation_id, _ = make_service(llm, FakeExecutor(MONTHLY)).ask("q", "no-such-id")

    assert conversation_id != "no-such-id"
    assert llm.sql_calls[0].history == ()


def test_prompt_hash_covers_the_notes_and_schema() -> None:
    llm = FakeAgentLLM()
    store = ConversationStore(max_turns=10, ttl=timedelta(minutes=60))
    base = AgentService(llm, FakeExecutor(), SCHEMA, "NOTES", store, max_retries=2, summary_rows=5)
    other = AgentService(llm, FakeExecutor(), SCHEMA, "OTHER", store, max_retries=2, summary_rows=5)

    assert len(base.prompt_hash) == 64
    assert base.prompt_hash != other.prompt_hash
    assert base.model_name == "fake"
