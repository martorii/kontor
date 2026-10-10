from dataclasses import dataclass
from typing import Literal

from kontor.domain.query import QueryResult

ChartType = Literal["bar", "line", "none"]
AgentStatus = Literal["answered", "gave_up"]


@dataclass(frozen=True, slots=True)
class ChartSpec:
    """How the UI should chart a result (CONTRACT §16.6). `x` and `y` are result columns."""

    type: ChartType
    x: str | None = None
    y: str | None = None


NO_CHART = ChartSpec("none")


@dataclass(frozen=True, slots=True)
class Summary:
    """The model's answer to a question, written from the query result."""

    answer: str
    chart: ChartSpec


@dataclass(frozen=True, slots=True)
class Turn:
    """One earlier question in a conversation. Rows are never kept (§16.7)."""

    question: str
    sql: str | None
    answer: str


@dataclass(frozen=True, slots=True)
class FailedAttempt:
    """SQL that failed validation or execution, or None when the model output was unusable."""

    sql: str | None
    error: str


@dataclass(frozen=True, slots=True)
class AgentAnswer:
    status: AgentStatus
    answer: str
    sql: str | None
    result: QueryResult | None
    chart: ChartSpec
    attempts: int
    last_error: str | None = None
