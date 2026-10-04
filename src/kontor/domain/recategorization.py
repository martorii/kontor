from collections.abc import Sequence
from dataclasses import dataclass

from kontor.domain.rule_engine import match_rule
from kontor.domain.rules import Rule
from kontor.domain.transaction import PreparedTransaction


@dataclass(frozen=True, slots=True)
class Candidate:
    """A stored transaction the rules are re-applied to."""

    transaction_id: int
    account_iban: str
    prepared: PreparedTransaction
    category_slug: str | None
    category_source: str | None  # None (uncategorized), "rule", "llm" or "manual"


@dataclass(frozen=True, slots=True)
class Change:
    """A new category (or none, when a rule stopped matching) for one transaction."""

    transaction_id: int
    old_category_slug: str | None
    old_category_source: str | None
    new_category_slug: str | None
    rule_id: str | None


@dataclass(frozen=True, slots=True)
class RerunResult:
    rules_hash: str
    dry_run: bool
    evaluated: int
    changes: tuple[Change, ...]


def _decide(candidate: Candidate, rule: Rule | None) -> Change | None:
    current = candidate.category_slug
    source = candidate.category_source
    if rule is not None:
        if source == "rule" and current == rule.category_slug:
            return None
        return Change(candidate.transaction_id, current, source, rule.category_slug, rule.id)
    if source == "rule":
        # The rule that categorized this transaction no longer matches: back to uncategorized.
        return Change(candidate.transaction_id, current, source, None, None)
    return None  # uncategorized stays so, and an LLM result is kept (CONTRACT §7.8)


def plan_rerun(
    candidates: Sequence[Candidate], rules: Sequence[Rule]
) -> tuple[int, tuple[Change, ...]]:
    """Decide what changes when the rules are re-applied. Manual categorizations are skipped."""
    evaluated = 0
    changes: list[Change] = []
    for candidate in candidates:
        if candidate.category_source == "manual":
            continue
        evaluated += 1
        rule = match_rule(rules, candidate.prepared, candidate.account_iban)
        change = _decide(candidate, rule)
        if change is not None:
            changes.append(change)
    return evaluated, tuple(changes)
