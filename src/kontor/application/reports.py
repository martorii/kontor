from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import date
from decimal import Decimal
from typing import Protocol

from kontor.domain.errors import InvalidDateRangeError, MixedCurrenciesError
from kontor.domain.reports import (
    CategorySpendingRow,
    CategoryTotal,
    DateBounds,
    ExplorerPage,
    MerchantTotal,
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

    def date_bounds(self, account_ids: Sequence[int] | None) -> DateBounds | None:
        with self._uow_factory() as uow:
            return uow.reports.date_bounds(account_ids)

    def top_merchants(
        self,
        date_from: date | None,
        date_to: date | None,
        account_ids: Sequence[int] | None,
        limit: int,
    ) -> TopMerchants:
        """A missing bound defaults to the first or last booking date available."""
        with self._uow_factory() as uow:
            bounds = uow.reports.date_bounds(account_ids)
            if bounds is None:
                return TopMerchants(date_from=None, date_to=None, currency=None, merchants=())
            start = date_from or bounds.first
            end = date_to or bounds.last
            if start > end:
                raise InvalidDateRangeError("the start date is after the end date")
            rows = uow.reports.top_merchants(start, end, account_ids, limit)
        return TopMerchants(
            date_from=start,
            date_to=end,
            currency=_currency(rows),
            merchants=tuple(MerchantTotal(r.merchant, r.spent, r.transaction_count) for r in rows),
        )

    def search_transactions(
        self, filters: TransactionFilter, limit: int, offset: int
    ) -> ExplorerPage:
        with self._uow_factory() as uow:
            return uow.transactions.search(filters, limit, offset)
