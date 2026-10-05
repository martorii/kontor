from types import TracebackType
from typing import Self

from sqlalchemy.orm import Session, sessionmaker

from kontor.adapters.db.repositories import (
    SqlAccountRepository,
    SqlCategoryRepository,
    SqlImportRepository,
    SqlReportRepository,
    SqlTransactionRepository,
)


class SqlUnitOfWork:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def __enter__(self) -> Self:
        self._session = self._session_factory()
        self.accounts = SqlAccountRepository(self._session)
        self.imports = SqlImportRepository(self._session)
        self.transactions = SqlTransactionRepository(self._session)
        self.categories = SqlCategoryRepository(self._session)
        self.reports = SqlReportRepository(self._session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._session.close()  # rolls back anything not committed

    def commit(self) -> None:
        self._session.commit()
