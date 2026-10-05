from collections.abc import Sequence

from kontor.domain.errors import LLMInvalidOutputError, LLMTimeoutError, LLMUnavailableError
from kontor.domain.llm import LLMSuggestion
from kontor.domain.transaction import Transaction


class FakeLLMClient:
    """Scripted LLM for tests. Answers by counterparty, or with `default`.

    Applies the same category-list check as the real adapter.
    """

    def __init__(
        self,
        answers: dict[str, LLMSuggestion] | None = None,
        default: LLMSuggestion | None = None,
        *,
        healthy: bool = True,
        timeout: bool = False,
    ) -> None:
        self._answers = answers or {}
        self._default = default
        self._healthy = healthy
        self._timeout = timeout
        self.calls: list[Transaction] = []

    def classify(self, transaction: Transaction, category_slugs: Sequence[str]) -> LLMSuggestion:
        self.calls.append(transaction)
        if not self._healthy:
            raise LLMUnavailableError("fake LLM is down")
        if self._timeout:
            raise LLMTimeoutError("fake LLM timed out")
        suggestion = self._answers.get(transaction.counterparty, self._default)
        if suggestion is None:
            raise LLMInvalidOutputError("fake LLM has no answer scripted")
        if suggestion.category_slug not in category_slugs:
            raise LLMInvalidOutputError(
                f"category {suggestion.category_slug!r} is not in the allowed list"
            )
        return suggestion

    def is_healthy(self) -> bool:
        return self._healthy
