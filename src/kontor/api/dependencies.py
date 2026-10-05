from fastapi import Request

from kontor.application.accounts import AccountService
from kontor.application.categorization import CategorizationService
from kontor.application.import_service import ImportService
from kontor.application.llm_step import LLMCategorizationStep


def get_import_service(request: Request) -> ImportService:
    service: ImportService = request.app.state.import_service
    return service


def get_account_service(request: Request) -> AccountService:
    service: AccountService = request.app.state.account_service
    return service


def get_categorization_service(request: Request) -> CategorizationService:
    service: CategorizationService = request.app.state.categorization_service
    return service


def get_llm_step(request: Request) -> LLMCategorizationStep:
    step: LLMCategorizationStep = request.app.state.llm_step
    return step
