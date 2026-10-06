from collections.abc import Callable, Sequence

import structlog

from kontor.domain.errors import InvalidCategoryError
from kontor.domain.review import ManualOverride, UncategorizedPage
from kontor.domain.rules import CategoryDef
from kontor.ports.repositories import UnitOfWork

log = structlog.get_logger()


class ReviewService:
    """The review tab's backend: list what is still open, and categorize by hand."""

    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def list_uncategorized(self, limit: int, offset: int) -> UncategorizedPage:
        with self._uow_factory() as uow:
            return uow.transactions.list_uncategorized_page(limit, offset)

    def list_subcategories(self) -> Sequence[CategoryDef]:
        """The categories a transaction can be assigned to."""
        with self._uow_factory() as uow:
            return uow.categories.list_subcategories()

    def set_category(self, transaction_id: int, category_slug: str) -> ManualOverride:
        """Override the category of any transaction. Raises InvalidCategoryError or
        TransactionNotFoundError."""
        with self._uow_factory() as uow:
            if not uow.categories.is_assignable(category_slug):
                raise InvalidCategoryError(f"'{category_slug}' is not a subcategory")
            override = uow.transactions.set_manual_category(transaction_id, category_slug)
            uow.imports.release_for_manual(override.import_id, override.previous_source)
            uow.commit()
        log.info(
            "manual_categorization",
            transaction_id=transaction_id,
            category=category_slug,
            previous_source=override.previous_source,
        )
        return override
