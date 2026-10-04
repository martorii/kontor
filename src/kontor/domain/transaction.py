from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Transaction:
    """A bank transaction as produced by a parser, before it is stored.

    Negative amounts are outflows.
    """

    booking_date: date
    amount: Decimal
    currency: str
    counterparty: str
    purpose: str
    value_date: date | None = None
    counterparty_iban: str | None = None
    raw: Mapping[str, str] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise TypeError("amount must be a Decimal, never a float")


@dataclass(frozen=True, slots=True)
class PreparedTransaction:
    """A parsed transaction with the values derived at import time."""

    transaction: Transaction
    counterparty_normalized: str
    fingerprint: str
