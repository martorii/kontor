from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

CategoryKind = Literal["expense", "income", "transfer", "savings"]
MatchField = Literal["counterparty", "purpose", "iban"]
MatchType = Literal["contains", "regex"]
AmountSign = Literal["negative", "positive"]


@dataclass(frozen=True, slots=True)
class CategoryDef:
    """One node of the two-level category tree.

    Top-level nodes have a kind, subcategories a parent.
    """

    slug: str
    name: str
    parent_slug: str | None
    kind: CategoryKind | None


def assignable_slugs(categories: Iterable[CategoryDef]) -> tuple[str, ...]:
    """The categories a transaction can be assigned to: the subcategories (CONTRACT §5.6)."""
    return tuple(c.slug for c in categories if c.parent_slug is not None)


@dataclass(frozen=True, slots=True)
class RuleConditions:
    amount_sign: AmountSign | None = None
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    account_iban: str | None = None


@dataclass(frozen=True, slots=True)
class Rule:
    id: str
    category_slug: str
    field: MatchField
    pattern: str
    match_type: MatchType
    conditions: RuleConditions


@dataclass(frozen=True, slots=True)
class RulesConfig:
    """The validated content of the rules file. Rule order is significant: first match wins."""

    categories: tuple[CategoryDef, ...]
    rules: tuple[Rule, ...]
    file_hash: str
