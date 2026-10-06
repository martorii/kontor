from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from kontor.api.dependencies import get_report_service, get_review_service
from kontor.api.schemas import (
    CategoryResponse,
    CategorySet,
    CategorySetResponse,
    UncategorizedPageResponse,
)
from kontor.application.reports import ReportService
from kontor.application.review import ReviewService
from kontor.domain.reports import CategorySource, ExplorerPage, TransactionFilter

router = APIRouter()

Service = Annotated[ReviewService, Depends(get_review_service)]


@router.get("/transactions")
def explore(
    service: Annotated[ReportService, Depends(get_report_service)],
    account_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    category: str | None = None,
    q: str | None = None,
    source: CategorySource | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ExplorerPage:
    """The transaction explorer. A top-level `category` includes its subcategories; a `source`
    of `none` means uncategorized."""
    filters = TransactionFilter(account_id, date_from, date_to, category, q, source)
    return service.search_transactions(filters, limit, offset)


@router.get("/categories")
def list_categories(service: Service) -> list[CategoryResponse]:
    """The assignable (sub)categories, for the UI's category pickers."""
    return [CategoryResponse.from_domain(c) for c in service.list_subcategories()]


@router.get("/transactions/uncategorized")
def list_uncategorized(
    service: Service,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UncategorizedPageResponse:
    return UncategorizedPageResponse.from_domain(
        service.list_uncategorized(limit, offset), limit, offset
    )


@router.put("/transactions/{transaction_id}/category")
def set_category(transaction_id: int, body: CategorySet, service: Service) -> CategorySetResponse:
    """Categorize by hand. Overrides any rule or LLM category (CONTRACT §7.7)."""
    service.set_category(transaction_id, body.category)
    return CategorySetResponse(
        transaction_id=transaction_id, category=body.category, source="manual"
    )
