from collections.abc import Sequence
from typing import Protocol

from kontor.domain.agent import FailedAttempt, Summary, Turn


class AgentLLM(Protocol):
    @property
    def model_name(self) -> str: ...

    @property
    def prompt_text(self) -> str:
        """Every fixed text the adapter sends (system prompts, message templates), for hashing."""
        ...

    def generate_sql(
        self,
        question: str,
        history: Sequence[Turn],
        context: str,
        failed_attempts: Sequence[FailedAttempt],
    ) -> str:
        """One SELECT answering `question`. `context` is the notes plus the schema.

        `failed_attempts` are this question's earlier attempts and why they failed.
        Raises LLMUnavailableError, LLMTimeoutError or LLMInvalidOutputError.
        """
        ...

    def summarize(
        self,
        question: str,
        sql: str,
        columns: Sequence[str],
        rows: Sequence[Sequence[object]],
        truncated: bool,
    ) -> Summary:
        """A short answer and a chart choice. `truncated` says there were more rows than shown.

        Raises LLMUnavailableError, LLMTimeoutError or LLMInvalidOutputError.
        """
        ...
