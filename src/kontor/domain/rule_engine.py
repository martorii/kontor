import re
from collections.abc import Sequence
from functools import lru_cache

from kontor.domain.normalization import normalize_purpose, normalize_text
from kontor.domain.rules import Rule, RuleConditions
from kontor.domain.transaction import PreparedTransaction


@lru_cache(maxsize=512)
def _regex(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


def _canonical_iban(iban: str) -> str:
    return iban.replace(" ", "").upper()


def _field_text(rule: Rule, prepared: PreparedTransaction) -> str | None:
    if rule.field == "counterparty":
        return prepared.counterparty_normalized
    if rule.field == "purpose":
        return normalize_purpose(prepared.transaction.purpose)
    iban = prepared.transaction.counterparty_iban
    return _canonical_iban(iban) if iban else None


def _text_matches(rule: Rule, text: str) -> bool:
    if rule.match_type == "regex":
        return _regex(rule.pattern).search(text) is not None
    if rule.field == "iban":
        return _canonical_iban(rule.pattern) in text
    # A pattern that normalizes to nothing (e.g. only digits) is matched as written.
    needle = normalize_text(rule.pattern) or rule.pattern.upper()
    return needle in text


def _conditions_hold(
    conditions: RuleConditions, prepared: PreparedTransaction, account_iban: str
) -> bool:
    amount = prepared.transaction.amount
    if conditions.amount_sign == "negative" and amount >= 0:
        return False
    if conditions.amount_sign == "positive" and amount <= 0:
        return False
    if conditions.amount_min is not None and amount < conditions.amount_min:
        return False
    if conditions.amount_max is not None and amount > conditions.amount_max:
        return False
    return not (
        conditions.account_iban is not None
        and _canonical_iban(conditions.account_iban) != _canonical_iban(account_iban)
    )


def match_rule(
    rules: Sequence[Rule], prepared: PreparedTransaction, account_iban: str
) -> Rule | None:
    """Return the first rule that matches, or None. Rule order is significant (CONTRACT §6.2)."""
    for rule in rules:
        text = _field_text(rule, prepared)
        if text is None or not _text_matches(rule, text):
            continue
        if _conditions_hold(rule.conditions, prepared, account_iban):
            return rule
    return None
