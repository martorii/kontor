from collections.abc import Mapping, Sequence
from types import TracebackType
from typing import Protocol, Self

from kontor.domain.account import Account, NewAccount
from kontor.domain.imports import ImportCounts, ImportRecord
from kontor.domain.recategorization import Candidate, Change
from kontor.domain.rules import CategoryDef
from kontor.domain.transaction import PreparedTransaction


class AccountRepository(Protocol):
    def get(self, account_id: int) -> Account | None: ...

    def get_by_iban(self, iban: str) -> Account | None: ...

    def list(self) -> list[Account]: ...

    def add(self, new: NewAccount) -> Account: ...

    def update(self, account_id: int, changes: Mapping[str, str]) -> Account:
        """Raises AccountNotFoundError or DuplicateIbanError."""
        ...


class ImportRepository(Protocol):
    def hash_exists(self, file_hash: str) -> bool: ...

    def add(self, account_id: int, file_name: str, file_hash: str) -> int:
        """Record a running import and return its id."""
        ...

    def complete(self, import_id: int, counts: ImportCounts) -> ImportRecord: ...


class TransactionRepository(Protocol):
    def existing_fingerprints(self, account_id: int, fingerprints: Sequence[str]) -> set[str]: ...

    def add_many(
        self, account_id: int, import_id: int, rows: Sequence[PreparedTransaction]
    ) -> None: ...

    def list_for_recategorization(self) -> list[Candidate]:
        """Every transaction that is not manually categorized."""
        ...

    def apply_rule_changes(self, changes: Sequence[Change], rules_hash: str) -> None:
        """Set the new category (source `rule`) and record one event per change."""
        ...


class CategoryRepository(Protocol):
    def upsert_all(self, categories: Sequence[CategoryDef]) -> None:
        """Insert new categories and update name, parent and kind of existing ones."""
        ...


class UnitOfWork(Protocol):
    """One database transaction. Leaving the block without commit() rolls everything back."""

    @property
    def accounts(self) -> AccountRepository: ...

    @property
    def imports(self) -> ImportRepository: ...

    @property
    def transactions(self) -> TransactionRepository: ...

    @property
    def categories(self) -> CategoryRepository: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...
