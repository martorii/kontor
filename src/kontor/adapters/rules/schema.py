import re
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from kontor.domain.rules import CategoryDef, Rule, RuleConditions

_Strict = ConfigDict(extra="forbid", frozen=True)
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)?$")]
NonEmpty = Annotated[str, StringConstraints(min_length=1)]


class CategorySchema(BaseModel):
    model_config = _Strict

    slug: Slug
    name: NonEmpty
    kind: Literal["expense", "income", "transfer", "savings"] | None = None
    parent: str | None = None

    @model_validator(mode="after")
    def _check_level(self) -> Self:
        if self.parent is None:
            if "." in self.slug:
                raise ValueError("a top-level slug must not contain a dot")
            if self.kind is None:
                raise ValueError("a top-level category needs a kind")
        else:
            if self.kind is not None:
                raise ValueError("a subcategory must not have a kind; it inherits its parent's")
            if not self.slug.startswith(f"{self.parent}."):
                raise ValueError(f"a subcategory slug must start with '{self.parent}.'")
        return self


class ConditionsSchema(BaseModel):
    model_config = _Strict

    amount_sign: Literal["negative", "positive"] | None = None
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    account: NonEmpty | None = Field(default=None, description="IBAN of the account")

    @model_validator(mode="after")
    def _check_range(self) -> Self:
        if (
            self.amount_min is not None
            and self.amount_max is not None
            and self.amount_min > self.amount_max
        ):
            raise ValueError("amount_min must not exceed amount_max")
        return self


class RuleSchema(BaseModel):
    model_config = _Strict

    id: NonEmpty
    category: Slug
    field: Literal["counterparty", "purpose", "iban"]
    match: NonEmpty
    type: Literal["contains", "regex"] = "contains"
    when: ConditionsSchema = ConditionsSchema()

    @model_validator(mode="after")
    def _check_regex(self) -> Self:
        if self.type == "regex":
            try:
                re.compile(self.match)
            except re.error as exc:
                raise ValueError(f"invalid regular expression: {exc}") from exc
        return self


class RulesFileSchema(BaseModel):
    model_config = _Strict

    categories: list[CategorySchema]
    rules: list[RuleSchema] = []

    @model_validator(mode="after")
    def _check_references(self) -> Self:
        by_slug: dict[str, CategorySchema] = {}
        for category in self.categories:
            if category.slug in by_slug:
                raise ValueError(f"duplicate category slug: {category.slug}")
            by_slug[category.slug] = category
        for category in self.categories:
            if category.parent is None:
                continue
            parent = by_slug.get(category.parent)
            if parent is None:
                raise ValueError(
                    f"category {category.slug}: parent '{category.parent}' does not exist"
                )
            if parent.parent is not None:
                raise ValueError(f"category {category.slug}: the tree has only two levels")

        rule_ids: set[str] = set()
        for rule in self.rules:
            if rule.id in rule_ids:
                raise ValueError(f"duplicate rule id: {rule.id}")
            rule_ids.add(rule.id)
            target = by_slug.get(rule.category)
            if target is None:
                raise ValueError(f"rule {rule.id}: unknown category '{rule.category}'")
            if target.parent is None:
                raise ValueError(f"rule {rule.id}: '{rule.category}' is not a subcategory")
        return self

    def to_domain(self) -> tuple[tuple[CategoryDef, ...], tuple[Rule, ...]]:
        categories = tuple(
            CategoryDef(
                slug=c.slug,
                name=c.name,
                parent_slug=c.parent,
                kind=c.kind,
            )
            for c in self.categories
        )
        rules = tuple(
            Rule(
                id=r.id,
                category_slug=r.category,
                field=r.field,
                pattern=r.match,
                match_type=r.type,
                conditions=RuleConditions(
                    amount_sign=r.when.amount_sign,
                    amount_min=r.when.amount_min,
                    amount_max=r.when.amount_max,
                    account_iban=r.when.account,
                ),
            )
            for r in self.rules
        )
        return categories, rules
