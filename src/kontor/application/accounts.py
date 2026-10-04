from collections.abc import Callable, Mapping

from kontor.domain.account import Account
from kontor.domain.errors import AccountNotFoundError
from kontor.ports.repositories import UnitOfWork


class AccountService:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def list(self) -> list[Account]:
        with self._uow_factory() as uow:
            return uow.accounts.list()

    def get(self, account_id: int) -> Account:
        with self._uow_factory() as uow:
            account = uow.accounts.get(account_id)
        if account is None:
            raise AccountNotFoundError(f"account {account_id} not found")
        return account

    def update(self, account_id: int, changes: Mapping[str, str]) -> Account:
        with self._uow_factory() as uow:
            account = uow.accounts.update(account_id, changes)
            uow.commit()
        return account
