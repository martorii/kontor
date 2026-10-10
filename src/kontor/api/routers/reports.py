from typing import Annotated

from fastapi import APIRouter, Depends, Query

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


@router.get("/top-merchants")
def top_merchants(
    service: Service,
    year: Year,
    month: Annotated[int | None, Query(ge=1, le=12)] = None,
    account_id: AccountId = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> TopMerchants:
    return service.top_merchants(year, month, account_id, limit)
