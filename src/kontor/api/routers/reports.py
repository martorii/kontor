from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from kontor.api.dependencies import get_report_service
from kontor.application.reports import ReportService
from kontor.domain.reports import (
    MonthlyOverview,
    TopMerchants,
    YearComparison,
)

router = APIRouter(prefix="/reports")

Service = Annotated[ReportService, Depends(get_report_service)]
Year = Annotated[int, Query(ge=1900, le=2200)]
AccountId = Annotated[int | None, Query()]
AccountIds = Annotated[list[int] | None, Query()]


class DateBoundsResponse(BaseModel):
    first: date | None
    last: date | None


@router.get("/monthly")
def monthly(
    service: Service,
    year: Year,
    month: Annotated[int, Query(ge=1, le=12)],
    account_id: AccountId = None,
) -> MonthlyOverview:
    return service.monthly_overview(year, month, account_id)


@router.get("/year")
def year_comparison(service: Service, year: Year, account_id: AccountId = None) -> YearComparison:
    return service.year_comparison(year, account_id)


@router.get("/date-bounds")
def date_bounds(service: Service, account_ids: AccountIds = None) -> DateBoundsResponse:
    bounds = service.date_bounds(account_ids)
    if bounds is None:
        return DateBoundsResponse(first=None, last=None)
    return DateBoundsResponse(first=bounds.first, last=bounds.last)


@router.get("/top-merchants")
def top_merchants(
    service: Service,
    date_from: date | None = None,
    date_to: date | None = None,
    account_ids: AccountIds = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> TopMerchants:
    return service.top_merchants(date_from, date_to, account_ids, limit)
