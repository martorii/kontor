from collections.abc import Sequence
from dataclasses import dataclass

from kontor.domain.agent import FailedAttempt, Summary, Turn
from kontor.domain.errors import LLMInvalidOutputError


@dataclass(frozen=True, slots=True)
class SqlCall:
    question: str
    history: tuple[Turn, ...]
    context: str
    failed_attempts: tuple[FailedAttempt, ...]


@dataclass(frozen=True, slots=True)
class SummaryCall:
    question: str
    sql: str
    columns: tuple[str, ...]
    rows: tuple[tuple[object, ...], ...]
    truncated: bool


class FakeAgentLLM:
    """Scripted agent LLM for tests. Each call takes the next scripted answer, in order.

    A scripted exception is raised instead of returned. Calls are recorded so tests can check
    what the agent sent. Running out of answers raises LLMInvalidOutputError.
    """

    model_name = "fake"
    prompt_text = "fake"

    def __init__(
        self,
        sql: Sequence[str | Exception] = (),
        summaries: Sequence[Summary | Exception] = (),
    ) -> None:
        self.sql = list(sql)
        self.summaries = list(summaries)
        self.sql_calls: list[SqlCall] = []
        self.summary_calls: list[SummaryCall] = []

    def generate_sql(
        self,
        question: str,
        history: Sequence[Turn],
        context: str,
        failed_attempts: Sequence[FailedAttempt],
    ) -> str:
        self.sql_calls.append(SqlCall(question, tuple(history), context, tuple(failed_attempts)))
        if not self.sql:
            raise LLMInvalidOutputError("fake agent LLM has no SQL scripted")
        answer = self.sql.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def summarize(
        self,
        question: str,
        sql: str,
        columns: Sequence[str],
        rows: Sequence[Sequence[object]],
        truncated: bool,
    ) -> Summary:
        self.summary_calls.append(
            SummaryCall(question, sql, tuple(columns), tuple(tuple(r) for r in rows), truncated)
        )
        if not self.summaries:
            raise LLMInvalidOutputError("fake agent LLM has no summary scripted")
        answer = self.summaries.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer
