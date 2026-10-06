from collections.abc import Sequence
from typing import Protocol

from kontor.domain.llm import LLMSuggestion
from kontor.domain.transaction import Transaction


class LLMClient(Protocol):
    @property
    def model_name(self) -> str: ...

    @property
    def prompt_hash(self) -> str:
        """Identifies the prompt text, so eval results can be tied to a prompt version."""
        ...

    def classify(self, transaction: Transaction, category_slugs: Sequence[str]) -> LLMSuggestion:
        """Pick one of `category_slugs` for the transaction.

        Raises LLMUnavailableError, LLMTimeoutError or LLMInvalidOutputError.
        """
        ...

    def is_healthy(self) -> bool:
        """True if the server is reachable. Never raises."""
        ...
