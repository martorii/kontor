import hashlib
from collections import Counter
from collections.abc import Sequence

from kontor.domain.normalization import normalize_counterparty
from kontor.domain.transaction import Transaction

_SEPARATOR = "\x1f"


def _identity(transaction: Transaction) -> tuple[str, str, str, str]:
    """The fields that make two transactions identical (everything but the occurrence index)."""
    return (
        transaction.booking_date.isoformat(),
        str(transaction.amount),
        normalize_counterparty(transaction.counterparty),
        " ".join(transaction.purpose.split()),
    )


def fingerprint(account: str, transaction: Transaction, occurrence: int) -> str:
    """SHA-256 over account, booking date, amount, normalized counterparty, purpose and the
    occurrence index within the group of identical transactions."""
    parts = (account, *_identity(transaction), str(occurrence))
    return hashlib.sha256(_SEPARATOR.join(parts).encode()).hexdigest()


def fingerprint_all(account: str, transactions: Sequence[Transaction]) -> list[str]:
    """Fingerprint a file's transactions in file order.

    Identical transactions are numbered 0, 1, 2, … in the order they appear, so genuine repeats
    stay distinct while overlapping exports reproduce the same fingerprints for shared rows.
    """
    seen: Counter[tuple[str, str, str, str]] = Counter()
    result: list[str] = []
    for transaction in transactions:
        key = _identity(transaction)
        result.append(fingerprint(account, transaction, seen[key]))
        seen[key] += 1
    return result
