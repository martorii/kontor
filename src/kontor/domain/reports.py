from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

CategorySource = Literal["rule", "llm", "manual", "none"]


# Rows as read from the SQL views.


@dataclass(frozen=True, slots=True)
class CategorySpendingRow:
    currency: str
    top_slug: str
    top_name: str
    sub_slug: str
    sub_name: str
    uncategorized: bool
    spent: Decimal
    transaction_count: int


@dataclass(frozen=True, slots=True)
class IncomeExpensesRow:
    currency: str
    month: int
    income: Decimal
    expenses: Decimal
    uncategorized_count: int


@dataclass(frozen=True, slots=True)
class MerchantRow:
    currency: str
    merchant: str
    spent: Decimal
    transaction_count: int


# Reports. Money is positive spending, so a refund reduces a total. Ratios are fractions.


@dataclass(frozen=True, slots=True)
class SubcategoryTotal:
    slug: str
    name: str
    total: Decimal
    transaction_count: int


@dataclass(frozen=True, slots=True)
class CategoryTotal:
    slug: str
    name: str
    total: Decimal
    uncategorized: bool
    subcategories: tuple[SubcategoryTotal, ...]


@dataclass(frozen=True, slots=True)
class MonthlyOverview:
    year: int
    month: int
    currency: str | None  # None when there is no data
    total: Decimal
    includes_uncategorized: bool  # provisional: uncategorized outflows are counted
    categories: tuple[CategoryTotal, ...]


@dataclass(frozen=True, slots=True)
class YearCategory:
    slug: str
    name: str
    total: Decimal
    previous_total: Decimal
    change: Decimal
    change_ratio: Decimal | None  # None when the previous total is zero


@dataclass(frozen=True, slots=True)
class YearComparison:
    year: int
    previous_year: int
    currency: str | None
    total: Decimal
    previous_total: Decimal
    change: Decimal
    includes_uncategorized: bool
    categories: tuple[YearCategory, ...]


@dataclass(frozen=True, slots=True)
class MonthIncomeExpenses:
    month: int
    income: Decimal
    expenses: Decimal
    net: Decimal
    savings_rate: Decimal | None  # (income - expenses) / income, None without income


@dataclass(frozen=True, slots=True)
class IncomeExpenses:
    year: int
    currency: str | None
    includes_uncategorized: bool
    income: Decimal
    expenses: Decimal
    net: Decimal
    savings_rate: Decimal | None
    months: tuple[MonthIncomeExpenses, ...]  # always 12


@dataclass(frozen=True, slots=True)
class MerchantTotal:
    merchant: str
    total: Decimal
    transaction_count: int


@dataclass(frozen=True, slots=True)
class TopMerchants:
    year: int
    month: int | None
    currency: str | None
    merchants: tuple[MerchantTotal, ...]


# Transaction explorer.


@dataclass(frozen=True, slots=True)
class TransactionFilter:
    account_id: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    category: str | None = None  # a top-level slug includes its subcategories
    text: str | None = None  # matches counterparty or purpose, case-insensitive
    source: CategorySource | None = None  # "none" means uncategorized


@dataclass(frozen=True, slots=True)
class ExplorerTransaction:
    transaction_id: int
    account_id: int
    booking_date: date
    amount: Decimal
    currency: str
    counterparty: str
    purpose: str
    category: str | None
    category_source: str | None


@dataclass(frozen=True, slots=True)
class ExplorerPage:
    total: int
    items: tuple[ExplorerTransaction, ...]
