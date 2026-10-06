from collections.abc import Sequence

from kontor.domain.errors import LLMInvalidOutputError, LLMTimeoutError, LLMUnavailableError
from kontor.domain.llm import LLMSuggestion
from kontor.domain.transaction import Transaction


class FakeLLMClient:
    """Scripted LLM for tests. Answers by counterparty, or with `default`.

    Applies the same category-list check as the real adapter. The attributes are public so a
    test can change the behaviour after the app was built.
    """

    model_name = "fake"
    prompt_hash = "fake"

    def __init__(
        self,
        answers: dict[str, LLMSuggestion] | None = None,
        default: LLMSuggestion | None = None,
        *,
        healthy: bool = True,
        timeout: bool = False,
        crash_on_call: int | None = None,
    ) -> None:
        self.answers = answers or {}
        self.default = default
        self.healthy = healthy
        self.timeout = timeout
        self.crash_on_call = crash_on_call  # 1-based call number that raises RuntimeError
        self.calls: list[Transaction] = []

    def classify(self, transaction: Transaction, category_slugs: Sequence[str]) -> LLMSuggestion:
        self.calls.append(transaction)
        if self.crash_on_call == len(self.calls):
            raise RuntimeError("fake LLM crashed")
        if not self.healthy:
            raise LLMUnavailableError("fake LLM is down")
        if self.timeout:
            raise LLMTimeoutError("fake LLM timed out")
        suggestion = self.answers.get(transaction.counterparty, self.default)
        if suggestion is None:
            raise LLMInvalidOutputError("fake LLM has no answer scripted")
        if suggestion.category_slug not in category_slugs:
            raise LLMInvalidOutputError(
                f"category {suggestion.category_slug!r} is not in the allowed list"
            )
        return suggestion

    def is_healthy(self) -> bool:
        return self.healthy
