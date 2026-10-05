from typing import Annotated

from fastapi import APIRouter, Depends

from kontor.api.dependencies import get_categorization_service, get_llm_step
from kontor.api.schemas import LLMRunResponse, RerunResponse
from kontor.application.categorization import CategorizationService
from kontor.application.llm_step import LLMCategorizationStep

router = APIRouter()


@router.post("/categorization/rerun")
def rerun(
    service: Annotated[CategorizationService, Depends(get_categorization_service)],
    dry_run: bool = False,
) -> RerunResponse:
    return RerunResponse.from_domain(service.rerun(dry_run))


@router.post("/categorization/llm")
def run_llm(
    step: Annotated[LLMCategorizationStep, Depends(get_llm_step)],
    dry_run: bool = False,
) -> LLMRunResponse:
    """Run the LLM step on every uncategorized transaction (CONTRACT §7.9)."""
    return LLMRunResponse.from_domain(step.run(dry_run=dry_run))
