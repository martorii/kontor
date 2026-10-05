from typing import Annotated

from fastapi import APIRouter, Depends, Query

from kontor.api.dependencies import get_review_service
from kontor.api.schemas import CategorySet, CategorySetResponse, UncategorizedPageResponse
from kontor.application.review import ReviewService

router = APIRouter()

Service = Annotated[ReviewService, Depends(get_review_service)]


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
