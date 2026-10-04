from typing import Annotated

from fastapi import APIRouter, Depends

from kontor.api.dependencies import get_account_service
from kontor.api.schemas import AccountResponse, AccountUpdate
from kontor.application.accounts import AccountService

router = APIRouter()

Service = Annotated[AccountService, Depends(get_account_service)]


@router.get("/accounts")
def list_accounts(service: Service) -> list[AccountResponse]:
    return [AccountResponse.from_domain(a) for a in service.list()]


@router.get("/accounts/{account_id}")
def get_account(account_id: int, service: Service) -> AccountResponse:
    return AccountResponse.from_domain(service.get(account_id))


@router.patch("/accounts/{account_id}")
def update_account(account_id: int, body: AccountUpdate, service: Service) -> AccountResponse:
    changes = body.model_dump(exclude_none=True)
    return AccountResponse.from_domain(service.update(account_id, changes))
