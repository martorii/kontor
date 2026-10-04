from datetime import date
from decimal import Decimal

import pytest

from kontor.domain.normalization import normalize_counterparty
from kontor.domain.rule_engine import match_rule
from kontor.domain.rules import (
    AmountSign,
    MatchField,
    MatchType,
    Rule,
    RuleConditions,
)
from kontor.domain.transaction import PreparedTransaction, Transaction

ACCOUNT = "DE89370400440532013000"


def prepared(
    counterparty: str = "REWE Markt GmbH",
    purpose: str = "Kartenzahlung",
    amount: str = "-20.00",
    iban: str | None = "DE02 1203 0000 0000 2020 51",
) -> PreparedTransaction:
    return PreparedTransaction(
        transaction=Transaction(
            booking_date=date(2026, 3, 12),
            amount=Decimal(amount),
            currency="EUR",
            counterparty=counterparty,
            purpose=purpose,
            counterparty_iban=iban,
        ),
        counterparty_normalized=normalize_counterparty(counterparty),
        fingerprint="f",
    )


def rule(
    pattern: str = "REWE",
    *,
    id: str = "r",
    field: MatchField = "counterparty",
    match_type: MatchType = "contains",
    category: str = "food.groceries",
    sign: AmountSign | None = None,
    amount_min: str | None = None,
    amount_max: str | None = None,
    account: str | None = None,
) -> Rule:
    return Rule(
        id=id,
        category_slug=category,
        field=field,
        pattern=pattern,
        match_type=match_type,
        conditions=RuleConditions(
            amount_sign=sign,
            amount_min=Decimal(amount_min) if amount_min else None,
            amount_max=Decimal(amount_max) if amount_max else None,
            account_iban=account,
        ),
    )


def matched_id(rules: list[Rule], tx: PreparedTransaction) -> str | None:
    found = match_rule(rules, tx, ACCOUNT)
    return found.id if found else None


# --- fields and match types -------------------------------------------------------------------


def test_contains_on_counterparty_is_case_insensitive() -> None:
    assert matched_id([rule("rewe")], prepared()) == "r"
    assert matched_id([rule("Rewe")], prepared(counterparty="REWE SAGT DANKE")) == "r"


def test_contains_runs_on_normalized_text() -> None:
    tx = prepared(counterparty="REWE FILIALE 1234 am 12.03.2026")
    assert matched_id([rule("REWE")], tx) == "r"
    # Store numbers are stripped, so a pattern containing them does not match.
    assert matched_id([rule("FILIALE 1234")], tx) is None


def test_contains_on_purpose() -> None:
    tx = prepared(purpose="SVWZ+ Miete Maerz 01.03.2026")
    assert matched_id([rule("miete", field="purpose")], tx) == "r"
    assert matched_id([rule("miete", field="counterparty")], tx) is None


def test_contains_on_iban_ignores_spaces_and_case() -> None:
    assert matched_id([rule("de0212030000", field="iban")], prepared()) == "r"
    assert matched_id([rule("DE02 1203", field="iban")], prepared()) == "r"
    assert matched_id([rule("DE99", field="iban")], prepared()) is None


def test_iban_rule_never_matches_a_transaction_without_iban() -> None:
    assert matched_id([rule("DE", field="iban")], prepared(iban=None)) is None
    assert matched_id([rule(".*", field="iban", match_type="regex")], prepared(iban=None)) is None


def test_regex_on_each_field() -> None:
    assert matched_id([rule(r"^REWE\b", match_type="regex")], prepared()) == "r"
    assert matched_id([rule(r"^MARKT", match_type="regex")], prepared()) is None
    tx = prepared(purpose="Rechnung 2026-17")
    assert matched_id([rule(r"RECHNUNG\s+\w+", field="purpose", match_type="regex")], tx) == "r"
    assert matched_id([rule(r"^DE99", field="iban", match_type="regex")], prepared()) is None
    assert matched_id([rule(r"^DE02", field="iban", match_type="regex")], prepared()) == "r"


def test_regex_is_case_insensitive() -> None:
    assert matched_id([rule("rewe", match_type="regex")], prepared()) == "r"


def test_pattern_that_normalizes_to_nothing_is_matched_as_written() -> None:
    assert matched_id([rule("12345678")], prepared(counterparty="Shop")) is None


# --- conditions -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sign", "amount", "expected"),
    [
        ("negative", "-0.01", True),
        ("negative", "5.00", False),
        ("negative", "0", False),
        ("positive", "5.00", True),
        ("positive", "-5.00", False),
        ("positive", "0", False),
    ],
)
def test_amount_sign(sign: AmountSign, amount: str, expected: bool) -> None:
    assert (matched_id([rule(sign=sign)], prepared(amount=amount)) == "r") is expected


@pytest.mark.parametrize(
    ("amount_min", "amount_max", "amount", "expected"),
    [
        ("-50", "-10", "-30", True),
        ("-50", "-10", "-10", True),  # inclusive
        ("-50", "-10", "-50", True),  # inclusive
        ("-50", "-10", "-9.99", False),
        ("-50", "-10", "-50.01", False),
        ("100", None, "100", True),
        ("100", None, "99.99", False),
        (None, "-10", "-10", True),
        (None, "-10", "-9", False),
    ],
)
def test_amount_range_is_signed(
    amount_min: str | None, amount_max: str | None, amount: str, expected: bool
) -> None:
    r = rule(amount_min=amount_min, amount_max=amount_max)
    assert (matched_id([r], prepared(amount=amount)) == "r") is expected


def test_account_condition() -> None:
    assert matched_id([rule(account=ACCOUNT)], prepared()) == "r"
    assert matched_id([rule(account="de89 3704 0044 0532 0130 00")], prepared()) == "r"
    assert matched_id([rule(account="DE02120300000000202051")], prepared()) is None


def test_all_conditions_must_hold() -> None:
    r = rule(sign="negative", amount_min="-50", account=ACCOUNT)
    assert matched_id([r], prepared(amount="-20")) == "r"
    assert matched_id([r], prepared(amount="-60")) is None
    assert matched_id([r], prepared(amount="20")) is None


def test_failed_condition_falls_through_to_the_next_rule() -> None:
    rules = [
        rule(id="big", sign="negative", amount_max="-100"),
        rule(id="small", sign="negative"),
    ]
    assert matched_id(rules, prepared(amount="-20")) == "small"
    assert matched_id(rules, prepared(amount="-200")) == "big"


# --- ordering ---------------------------------------------------------------------------------


def test_first_matching_rule_wins() -> None:
    rules = [
        rule("REWE", id="first", category="food.groceries"),
        rule("REWE", id="second", category="shopping.home"),
    ]
    found = match_rule(rules, prepared(), ACCOUNT)
    assert found is not None
    assert (found.id, found.category_slug) == ("first", "food.groceries")


def test_order_matters_when_rules_overlap() -> None:
    specific = rule("REWE MARKT", id="specific")
    broad = rule("REWE", id="broad")
    assert matched_id([specific, broad], prepared()) == "specific"
    assert matched_id([broad, specific], prepared()) == "broad"


def test_no_match_and_no_rules() -> None:
    assert matched_id([rule("EDEKA")], prepared()) is None
    assert matched_id([], prepared()) is None
