"""The text-to-SQL agent (CONTRACT §16): generate SQL, validate, execute, summarize.

A failed validation, execution or unusable model output goes back to `generate_sql` with the
error, at most `max_retries` times; then the agent gives up. SQL that fails validation never
reaches the executor. LM Studio being down or slow propagates as LLMUnavailableError or
LLMTimeoutError, for the API to map.
"""

from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Literal, TypedDict

import structlog
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from kontor.application.agent_context import prompt_hash, render_schema
from kontor.application.agent_conversations import ConversationStore
from kontor.application.sql_validator import validate_query
from kontor.domain.agent import (
    NO_CHART,
    AgentAnswer,
    AttemptRecord,
    ChartSpec,
    FailedAttempt,
    Summary,
    Turn,
)
from kontor.domain.errors import (
    ConversationNotFoundError,
    LLMInvalidOutputError,
    QueryExecutionError,
    QueryTimeoutError,
    UnsafeQueryError,
)
from kontor.domain.query import QueryResult
from kontor.domain.schema import SchemaInfo
from kontor.ports.agent_llm import AgentLLM
from kontor.ports.query_executor import QueryExecutor

log = structlog.get_logger()

FALLBACK_ANSWER = "Here are the results."
GAVE_UP_ANSWER = "I could not write a working query for this question."

_Node = Literal["generate_sql", "validate", "execute", "summarize"]


class _State(TypedDict):
    question: str
    history: tuple[Turn, ...]
    attempts: int
    failed: tuple[FailedAttempt, ...]
    sql: str | None
    error: str | None
    result: QueryResult | None
    summary: Summary | None


def check_chart(chart: ChartSpec, result: QueryResult) -> ChartSpec:
    """Keep the model's chart only if it fits the result: known columns, numeric y."""
    if chart.type == "none":
        return NO_CHART
    if chart.x not in result.columns or chart.y not in result.columns:
        return NO_CHART
    y_index = result.columns.index(chart.y)
    values = [row[y_index] for row in result.rows if row[y_index] is not None]
    if not values or not all(_is_number(value) for value in values):
        return NO_CHART
    return chart


def _is_number(value: object) -> bool:
    return isinstance(value, int | float | Decimal) and not isinstance(value, bool)


class AgentGraph:
    def __init__(
        self,
        llm: AgentLLM,
        executor: QueryExecutor,
        allowed_relations: frozenset[str],
        context: str,
        *,
        max_retries: int,
        summary_rows: int,
    ) -> None:
        self._llm = llm
        self._executor = executor
        self._allowed_relations = allowed_relations
        self._context = context
        self._max_attempts = max_retries + 1
        self._summary_rows = summary_rows
        self._graph = self._build()

    def run(self, question: str, history: Sequence[Turn]) -> AgentAnswer:
        initial: _State = {
            "question": question,
            "history": tuple(history),
            "attempts": 0,
            "failed": (),
            "sql": None,
            "error": None,
            "result": None,
            "summary": None,
        }
        # Each attempt passes at most three nodes, plus the summary; leave headroom.
        final = self._graph.invoke(initial, {"recursion_limit": 4 * self._max_attempts + 5})
        summary = final["summary"]
        result = final["result"]
        # Each attempt fails at most once, so the failures are attempts 1..n in order.
        trace = tuple(
            AttemptRecord(number, failed.sql, failed.error, None)
            for number, failed in enumerate(final["failed"], start=1)
        )
        if summary is None or result is None:
            last = final["failed"][-1]
            log.info("agent_gave_up", attempts=final["attempts"], error=last.error)
            return AgentAnswer(
                status="gave_up",
                answer=GAVE_UP_ANSWER,
                sql=last.sql,
                result=None,
                chart=NO_CHART,
                attempts=final["attempts"],
                last_error=last.error,
                trace=trace,
            )
        return AgentAnswer(
            status="answered",
            answer=summary.answer,
            sql=final["sql"],
            result=result,
            chart=summary.chart,
            attempts=final["attempts"],
            trace=(
                *trace,
                AttemptRecord(final["attempts"], final["sql"], None, len(result.rows)),
            ),
        )

    def _build(self) -> CompiledStateGraph[_State, None, _State, _State]:
        graph = StateGraph(_State)
        graph.add_node("generate_sql", self._generate_sql)
        graph.add_node("validate", self._validate)
        graph.add_node("execute", self._execute)
        graph.add_node("summarize", self._summarize)
        graph.add_edge(START, "generate_sql")
        graph.add_conditional_edges("generate_sql", self._next("validate"))
        graph.add_conditional_edges("validate", self._next("execute"))
        graph.add_conditional_edges("execute", self._next("summarize"))
        graph.add_edge("summarize", END)
        return graph.compile()

    def _next(self, on_success: _Node) -> Callable[[_State], str]:
        def route(state: _State) -> str:
            if state["error"] is None:
                return on_success
            return "generate_sql" if state["attempts"] < self._max_attempts else END

        return route

    def _fail(
        self, state: _State, error: str, *, attempt: int, sql: str | None
    ) -> dict[str, object]:
        log.info("agent_attempt_failed", attempt=attempt, error=error)
        return {"error": error, "failed": (*state["failed"], FailedAttempt(sql, error))}

    def _generate_sql(self, state: _State) -> dict[str, object]:
        attempt = state["attempts"] + 1
        update: dict[str, object] = {"attempts": attempt, "sql": None, "error": None}
        try:
            sql = self._llm.generate_sql(
                state["question"], state["history"], self._context, state["failed"]
            )
        except LLMInvalidOutputError as exc:
            error = f"unusable model output: {exc}"
            return update | self._fail(state, error, attempt=attempt, sql=None)
        log.info("agent_sql_generated", attempt=attempt)
        log.debug("agent_sql", attempt=attempt, sql=sql)
        return update | {"sql": sql}

    def _validate(self, state: _State) -> dict[str, object]:
        assert state["sql"] is not None  # routed here only after SQL was generated
        try:
            validate_query(state["sql"], self._allowed_relations)
        except UnsafeQueryError as exc:
            error = f"rejected by the validator: {exc}"
            return self._fail(state, error, attempt=state["attempts"], sql=state["sql"])
        return {}

    def _execute(self, state: _State) -> dict[str, object]:
        assert state["sql"] is not None  # routed here only after validation passed
        try:
            result = self._executor.execute(state["sql"])
        except QueryTimeoutError as exc:
            error = f"the query timed out: {exc}"
            return self._fail(state, error, attempt=state["attempts"], sql=state["sql"])
        except QueryExecutionError as exc:
            error = f"Postgres error: {exc}"
            return self._fail(state, error, attempt=state["attempts"], sql=state["sql"])
        log.info(
            "agent_sql_executed",
            attempt=state["attempts"],
            rows=len(result.rows),
            truncated=result.truncated,
        )
        return {"result": result}

    def _summarize(self, state: _State) -> dict[str, object]:
        result = state["result"]
        assert result is not None and state["sql"] is not None  # routed here after execution
        shown = result.rows[: self._summary_rows]
        try:
            summary = self._llm.summarize(
                state["question"],
                state["sql"],
                result.columns,
                shown,
                result.truncated or len(shown) < len(result.rows),
            )
        except LLMInvalidOutputError as exc:
            log.info("agent_summary_unusable", error=str(exc))
            summary = Summary(FALLBACK_ANSWER, NO_CHART)
        return {"summary": Summary(summary.answer, check_chart(summary.chart, result))}


class AgentService:
    """Answers questions within conversations, using the notes and the introspected schema."""

    def __init__(
        self,
        llm: AgentLLM,
        executor: QueryExecutor,
        schema: SchemaInfo,
        notes: str,
        store: ConversationStore,
        *,
        max_retries: int,
        summary_rows: int,
    ) -> None:
        schema_text = render_schema(schema)
        self._llm = llm
        self._store = store
        self._graph = AgentGraph(
            llm,
            executor,
            schema.allowed_relations,
            f"{notes}\n\n# Schema\n\n{schema_text}",
            max_retries=max_retries,
            summary_rows=summary_rows,
        )
        self.prompt_hash = prompt_hash(llm.prompt_text, notes, schema_text)

    @property
    def model_name(self) -> str:
        return self._llm.model_name

    def forget(self, conversation_id: str) -> None:
        """Drop a conversation. Raises ConversationNotFoundError if it does not exist."""
        if not self._store.delete(conversation_id):
            raise ConversationNotFoundError(conversation_id)

    def ask(self, question: str, conversation_id: str | None) -> tuple[str, AgentAnswer]:
        """Answer `question`. An unknown or expired conversation id starts a new conversation."""
        history = self._store.history(conversation_id) if conversation_id else None
        if conversation_id is None or history is None:
            conversation_id = self._store.start()
            history = ()
        with structlog.contextvars.bound_contextvars(conversation_id=conversation_id):
            log.info("agent_question", turns=len(history))
            answer = self._graph.run(question, history)
            log.info("agent_answered", status=answer.status, attempts=answer.attempts)
        self._store.append(conversation_id, Turn(question, answer.sql, answer.answer))
        return conversation_id, answer
