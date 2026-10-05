from typing import Annotated

from fastapi import APIRouter, Depends

from kontor.api.dependencies import get_categorization_service
from kontor.api.schemas import RerunResponse
from kontor.application.categorization import CategorizationService

router = APIRouter()


@router.post("/categorization/rerun")
def rerun(
    service: Annotated[CategorizationService, Depends(get_categorization_service)],
    dry_run: bool = False,
) -> RerunResponse:
    return RerunResponse.from_domain(service.rerun(dry_run))
