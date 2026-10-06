from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class LabeledExample:
    """One manually categorized transaction: the input the LLM sees and the true category."""

    counterparty: str
    purpose: str
    amount: Decimal
    currency: str
    category_slug: str


@dataclass(frozen=True, slots=True)
class EvalCase:
    """The LLM's answer for one labeled example. `predicted` is None when the call failed."""

    expected: str
    predicted: str | None
    confidence: float | None
    latency_seconds: float


@dataclass(frozen=True, slots=True)
class EvalMetrics:
    """CONTRACT §12.3. Ratios are fractions, None when their denominator is zero."""

    total: int  # labeled examples evaluated
    answered: int  # the LLM returned a category
    failed: int  # timeout, unreachable or invalid output
    top_level_accuracy: float | None
    subcategory_accuracy: float | None
    threshold: float
    coverage: float | None  # share of answered with confidence >= threshold
    covered_accuracy: float | None  # subcategory accuracy among the covered
    average_latency_seconds: float | None


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def compute_metrics(
    cases: Sequence[EvalCase], parents: Mapping[str, str | None], threshold: float
) -> EvalMetrics:
    """`parents` maps each subcategory slug to its top-level slug."""
    answered = [c for c in cases if c.predicted is not None and c.confidence is not None]
    covered = [c for c in answered if (c.confidence or 0.0) >= threshold]
    return EvalMetrics(
        total=len(cases),
        answered=len(answered),
        failed=len(cases) - len(answered),
        top_level_accuracy=_ratio(
            sum(1 for c in answered if parents.get(c.predicted or "") == parents.get(c.expected)),
            len(answered),
        ),
        subcategory_accuracy=_ratio(
            sum(1 for c in answered if c.predicted == c.expected), len(answered)
        ),
        threshold=threshold,
        coverage=_ratio(len(covered), len(answered)),
        covered_accuracy=_ratio(sum(1 for c in covered if c.predicted == c.expected), len(covered)),
        average_latency_seconds=(
            sum(c.latency_seconds for c in answered) / len(answered) if answered else None
        ),
    )
