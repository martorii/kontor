from fastapi import Request

from kontor.application.accounts import AccountService
from kontor.application.import_service import ImportService


def get_import_service(request: Request) -> ImportService:
    service: ImportService = request.app.state.import_service
    return service


def get_account_service(request: Request) -> AccountService:
    service: AccountService = request.app.state.account_service
    return service
