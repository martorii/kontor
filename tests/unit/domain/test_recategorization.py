from datetime import date
from decimal import Decimal

from kontor.domain.normalization import normalize_counterparty
from kontor.domain.recategorization import Candidate, plan_rerun
from kontor.domain.rules import Rule, RuleConditions
from kontor.domain.transaction import PreparedTransaction, Transaction

ACCOUNT = "DE89370400440532013000"


def rule(rule_id: str, pattern: str, category: str) -> Rule:
    return Rule(rule_id, category, "counterparty", pattern, "contains", RuleConditions())


def candidate(tx_id: int, counterparty: str, category: str | None, source: str | None) -> Candidate:
    transaction = Transaction(
        booking_date=date(2026, 3, 12),
        amount=Decimal("-10.00"),
        currency="EUR",
        counterparty=counterparty,
        purpose="x",
    )
    return Candidate(
        transaction_id=tx_id,
        account_iban=ACCOUNT,
        prepared=PreparedTransaction(transaction, normalize_counterparty(counterparty), "f"),
        category_slug=category,
        category_source=source,
    )


RULES = [rule("rewe", "REWE", "food.groceries")]


def test_uncategorized_matching_a_rule_is_categorized() -> None:
    evaluated, changes = plan_rerun([candidate(1, "REWE", None, None)], RULES)

    assert evaluated == 1
    (change,) = changes
    assert (change.new_category_slug, change.rule_id) == ("food.groceries", "rewe")


def test_rule_replaces_llm_result() -> None:
    _, changes = plan_rerun([candidate(1, "REWE", "shopping.home", "llm")], RULES)

    (change,) = changes
    assert (change.old_category_slug, change.old_category_source) == ("shopping.home", "llm")
    assert (change.new_category_slug, change.rule_id) == ("food.groceries", "rewe")


def test_llm_result_is_kept_without_a_matching_rule() -> None:
    evaluated, changes = plan_rerun([candidate(1, "Unknown", "shopping.home", "llm")], RULES)

    assert evaluated == 1
    assert changes == ()


def test_uncategorized_without_a_match_stays_uncategorized() -> None:
    assert plan_rerun([candidate(1, "Unknown", None, None)], RULES)[1] == ()


def test_manual_categorization_is_skipped() -> None:
    evaluated, changes = plan_rerun([candidate(1, "REWE", "shopping.home", "manual")], RULES)

    assert evaluated == 0
    assert changes == ()


def test_unchanged_rule_result_is_not_a_change() -> None:
    assert plan_rerun([candidate(1, "REWE", "food.groceries", "rule")], RULES)[1] == ()


def test_rule_result_changes_when_the_rule_now_says_something_else() -> None:
    _, changes = plan_rerun([candidate(1, "REWE", "shopping.home", "rule")], RULES)

    assert [c.new_category_slug for c in changes] == ["food.groceries"]


def test_rule_result_is_reset_when_no_rule_matches_anymore() -> None:
    _, changes = plan_rerun([candidate(1, "REWE", "food.groceries", "rule")], [])

    (change,) = changes
    assert (change.new_category_slug, change.rule_id) == (None, None)
    assert change.old_category_source == "rule"
