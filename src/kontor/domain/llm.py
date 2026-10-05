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
