from collections.abc import Mapping, Sequence
from datetime import date
from types import TracebackType
from typing import Protocol, Self

from kontor.domain.account import Account, NewAccount
from kontor.domain.imports import ImportCounts, ImportRecord
from kontor.domain.llm import LLMOutcome
from kontor.domain.recategorization import Candidate, Change
from kontor.domain.reports import (
    CategorySpendingRow,
    DateBounds,
    ExplorerPage,
    MerchantRow,
    TransactionFilter,
)
from kontor.domain.review import ManualOverride, UncategorizedPage
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

    def list(self) -> list[ImportRecord]:
        """Every import, newest first."""
        ...

    def release_for_manual(self, import_id: int, previous_source: str | None) -> None:
        """A transaction of this import became manual: drop it from the count it was in."""
        ...

    def move_to_llm_matched(self, counts_by_import: Mapping[int, int]) -> None:
        """Per import, move that many transactions from uncategorized to LLM-matched."""
        ...


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

    def list_uncategorized(self, import_id: int | None = None) -> list[Candidate]:
        """Transactions with no category (suggestions do not count), optionally of one import."""
        ...

    def list_uncategorized_page(self, limit: int, offset: int) -> UncategorizedPage:
        """Uncategorized transactions with their unapplied LLM suggestions, newest first."""
        ...

    def search(self, filters: TransactionFilter, limit: int, offset: int) -> ExplorerPage:
        """The transaction explorer: filtered, newest first."""
        ...

    def set_manual_category(self, transaction_id: int, category_slug: str) -> ManualOverride:
        """Assign the category (source `manual`) and record the event.

        Raises TransactionNotFoundError.
        """
        ...

    def apply_llm_outcomes(self, outcomes: Sequence[LLMOutcome], model_name: str) -> dict[int, int]:
        """Record one event per outcome that has a suggestion. Assign the category (source
        `llm`) where the outcome is applied and the transaction is still uncategorized.
        Returns, per import id, how many transactions were categorized."""
        ...


class ReportRepository(Protocol):
    def category_spending(
        self, year: int, month: int | None, account_id: int | None
    ) -> list[CategorySpendingRow]: ...

    def top_merchants(
        self, date_from: date, date_to: date, account_ids: Sequence[int] | None, limit: int
    ) -> list[MerchantRow]: ...

    def date_bounds(self, account_ids: Sequence[int] | None) -> DateBounds | None:
        """First and last booking date, or None if there are no transactions."""
        ...


class CategoryRepository(Protocol):
    def is_assignable(self, slug: str) -> bool:
        """True if the category exists and is a subcategory."""
        ...

    def list_subcategories(self) -> Sequence[CategoryDef]:
        """Every subcategory, ordered by parent slug, then slug."""
        ...

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

    @property
    def reports(self) -> ReportRepository: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...
