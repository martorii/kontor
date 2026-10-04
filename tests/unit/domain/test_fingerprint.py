from datetime import date
from decimal import Decimal

import pytest

from kontor.domain.fingerprint import fingerprint_all
from kontor.domain.transaction import Transaction

ACCOUNT = "DE00000000000000000000"


def tx(
    day: int = 12,
    amount: str = "-3.50",
    counterparty: str = "Baeckerei Mueller",
    purpose: str = "Kaffee",
) -> Transaction:
    return Transaction(
        booking_date=date(2026, 3, day),
        amount=Decimal(amount),
        currency="EUR",
        counterparty=counterparty,
        purpose=purpose,
    )


def test_fingerprint_is_stable() -> None:
    assert fingerprint_all(ACCOUNT, [tx()]) == fingerprint_all(ACCOUNT, [tx()])


def test_fingerprint_ignores_counterparty_noise() -> None:
    a = fingerprint_all(ACCOUNT, [tx(counterparty="REWE FILIALE 12")])
    b = fingerprint_all(ACCOUNT, [tx(counterparty="rewe filiale 99")])
    assert a == b


@pytest.mark.parametrize(
    "other",
    [tx(day=13), tx(amount="-3.60"), tx(counterparty="Other"), tx(purpose="Brot")],
)
def test_different_fields_change_the_fingerprint(other: Transaction) -> None:
    assert fingerprint_all(ACCOUNT, [tx()]) != fingerprint_all(ACCOUNT, [other])


def test_account_changes_the_fingerprint() -> None:
    assert fingerprint_all("A", [tx()]) != fingerprint_all("B", [tx()])


def test_identical_same_day_transactions_get_distinct_fingerprints() -> None:
    fingerprints = fingerprint_all(ACCOUNT, [tx(), tx(), tx()])
    assert len(set(fingerprints)) == 3


def test_overlapping_input_shares_fingerprints() -> None:
    export_a = [tx(day=10), tx(day=12), tx(day=12), tx(day=14)]
    export_b = [tx(day=12), tx(day=12), tx(day=14), tx(day=20)]
    a = fingerprint_all(ACCOUNT, export_a)
    b = fingerprint_all(ACCOUNT, export_b)
    assert set(a[1:]) == set(b[:3])
    assert set(a) & set(b) == set(a[1:])


def test_later_export_with_extra_identical_row_adds_only_that_row() -> None:
    earlier = fingerprint_all(ACCOUNT, [tx()])
    later = fingerprint_all(ACCOUNT, [tx(), tx()])
    assert later[0] == earlier[0]
    assert later[1] not in earlier


def test_amount_must_be_decimal() -> None:
    with pytest.raises(TypeError):
        Transaction(
            booking_date=date(2026, 3, 1),
            amount=1.5,  # type: ignore[arg-type]
            currency="EUR",
            counterparty="x",
            purpose="y",
        )
