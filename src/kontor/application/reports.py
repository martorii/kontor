from collections import defaultdict
from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Protocol

from kontor.domain.errors import MixedCurrenciesError
from kontor.domain.reports import (
    CategorySpendingRow,
    CategoryTotal,
    ExplorerPage,
    IncomeExpenses,
    MerchantTotal,
    MonthIncomeExpenses,
    MonthlyOverview,
    SubcategoryTotal,
    TopMerchants,
    TransactionFilter,
    YearCategory,
    YearComparison,
)
from kontor.ports.repositories import UnitOfWork


class Currency(Protocol):
    @property
    def currency(self) -> str: ...


ZERO = Decimal(0)
RATIO = Decimal("0.0001")


def _currency(rows: Sequence[Currency]) -> str | None:
    currencies = {row.currency for row in rows}
    if len(currencies) > 1:
        raise MixedCurrenciesError("the data has several currencies; select one account")
    return next(iter(currencies), None)


def _ratio(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator == 0:
        return None
    return (numerator / denominator).quantize(RATIO)


class ReportService:
    """Shapes the rows of the SQL views into reports. The sums happen in SQL (CONTRACT §11.3)."""

    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def monthly_overview(self, year: int, month: int, account_id: int | None) -> MonthlyOverview:
        with self._uow_factory() as uow:
            rows = uow.reports.category_spending(year, month, account_id)
        currency = _currency(rows)
        by_top: dict[str, list[CategorySpendingRow]] = defaultdict(list)
        for row in rows:
            by_top[row.top_slug].append(row)
        categories = sorted(
            (
                CategoryTotal(
                    slug=slug,
                    name=group[0].top_name,
                    total=sum((r.spent for r in group), ZERO),
                    uncategorized=group[0].uncategorized,
                    subcategories=tuple(
                        sorted(
                            (
                                SubcategoryTotal(
                                    r.sub_slug, r.sub_name, r.spent, r.transaction_count
                                )
                                for r in group
                            ),
                            key=lambda s: (-s.total, s.slug),
                        )
                    ),
                )
                for slug, group in by_top.items()
            ),
            key=lambda c: (-c.total, c.slug),
        )
        return MonthlyOverview(
            year=year,
            month=month,
            currency=currency,
            total=sum((c.total for c in categories), ZERO),
            includes_uncategorized=any(r.uncategorized for r in rows),
            categories=tuple(categories),
        )

    def year_comparison(self, year: int, account_id: int | None) -> YearComparison:
        with self._uow_factory() as uow:
            current = uow.reports.category_spending(year, None, account_id)
            previous = uow.reports.category_spending(year - 1, None, account_id)
        currency = _currency([*current, *previous])
        names: dict[str, str] = {}
        totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
        previous_totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for rows, target in ((current, totals), (previous, previous_totals)):
            for row in rows:
                names[row.top_slug] = row.top_name
                target[row.top_slug] += row.spent
        categories = sorted(
            (
                YearCategory(
                    slug=slug,
                    name=name,
                    total=totals[slug],
                    previous_total=previous_totals[slug],
                    change=totals[slug] - previous_totals[slug],
                    change_ratio=_ratio(
                        totals[slug] - previous_totals[slug], previous_totals[slug]
                    ),
                )
                for slug, name in names.items()
            ),
            key=lambda c: (-c.total, -c.previous_total, c.slug),
        )
        total = sum(totals.values(), ZERO)
        previous_total = sum(previous_totals.values(), ZERO)
        return YearComparison(
            year=year,
            previous_year=year - 1,
            currency=currency,
            total=total,
            previous_total=previous_total,
            change=total - previous_total,
            includes_uncategorized=any(r.uncategorized for r in [*current, *previous]),
            categories=tuple(categories),
        )

    def income_expenses(self, year: int, account_id: int | None) -> IncomeExpenses:
        with self._uow_factory() as uow:
            rows = uow.reports.income_expenses(year, account_id)
        currency = _currency(rows)
        by_month = {row.month: row for row in rows}
        months = []
        for month in range(1, 13):
            row = by_month.get(month)
            income = row.income if row else ZERO
            expenses = row.expenses if row else ZERO
            months.append(
                MonthIncomeExpenses(
                    month=month,
                    income=income,
                    expenses=expenses,
                    net=income - expenses,
                    savings_rate=_ratio(income - expenses, income),
                )
            )
        income = sum((m.income for m in months), ZERO)
        expenses = sum((m.expenses for m in months), ZERO)
        return IncomeExpenses(
            year=year,
            currency=currency,
            includes_uncategorized=any(r.uncategorized_count for r in rows),
            income=income,
            expenses=expenses,
            net=income - expenses,
            savings_rate=_ratio(income - expenses, income),
            months=tuple(months),
        )

    def top_merchants(
        self, year: int, month: int | None, account_id: int | None, limit: int
    ) -> TopMerchants:
        with self._uow_factory() as uow:
            rows = uow.reports.top_merchants(year, month, account_id, limit)
        return TopMerchants(
            year=year,
            month=month,
            currency=_currency(rows),
            merchants=tuple(MerchantTotal(r.merchant, r.spent, r.transaction_count) for r in rows),
        )

    def search_transactions(
        self, filters: TransactionFilter, limit: int, offset: int
    ) -> ExplorerPage:
        with self._uow_factory() as uow:
            return uow.transactions.search(filters, limit, offset)
