import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LLMSuggestion:
    """The LLM's category choice for one transaction.

    `confidence` is the model's own probability of the chosen category (CONTRACT §7.4),
    derived from token logprobs, never a number the model reports about itself.
    """

    category_slug: str
    confidence: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be within [0, 1]")


@dataclass(frozen=True, slots=True)
class LLMOutcome:
    """The result of the LLM step for one transaction.

    `suggestion` is None when the call failed (`error` says why). `applied` is True when the
    confidence reached the threshold and the category was assigned.
    """

    transaction_id: int
    suggestion: LLMSuggestion | None
    applied: bool
    error: str | None = None


@dataclass(frozen=True, slots=True)
class LLMRunResult:
    dry_run: bool
    skipped: bool = False  # LM Studio unreachable (CONTRACT §8.5)
    interrupted: bool = False  # stopped early; committed batches are kept (§8.4)
    evaluated: int = 0
    applied: int = 0
    suggested: int = 0  # below the threshold, stored as suggestions only
    failed: int = 0
    outcomes: tuple[LLMOutcome, ...] = ()


@dataclass(frozen=True, slots=True)
class LLMProgress:
    """A snapshot of the running LLM step: how many transactions are done out of the total."""

    running: bool = False
    processed: int = 0
    total: int = 0
    import_id: int | None = None  # None for a run over all uncategorized transactions
