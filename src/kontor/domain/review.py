from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Suggestion:
    """An LLM answer that stayed below the threshold and was not applied."""

    category_slug: str | None
    confidence: float | None
    model_name: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class UncategorizedTransaction:
    transaction_id: int
    account_id: int
    booking_date: date
    amount: Decimal
    currency: str
    counterparty: str
    purpose: str
    suggestions: tuple[Suggestion, ...]  # newest first


@dataclass(frozen=True, slots=True)
class UncategorizedPage:
    total: int
    items: tuple[UncategorizedTransaction, ...]


@dataclass(frozen=True, slots=True)
class ManualOverride:
    """What a manual categorization replaced, to keep the import counts consistent."""

    transaction_id: int
    import_id: int
    previous_source: str | None  # None (uncategorized), "rule", "llm" or "manual"
