from collections.abc import Callable

import structlog

from kontor.domain.rules import CategoryDef
from kontor.ports.repositories import UnitOfWork

log = structlog.get_logger()


def sync_categories(
    uow_factory: Callable[[], UnitOfWork], categories: tuple[CategoryDef, ...]
) -> None:
    """Upsert the category tree into the database. Idempotent; never deletes a category,
    because transactions may still reference it."""
    with uow_factory() as uow:
        uow.categories.upsert_all(categories)
        uow.commit()
    log.info("categories_synced", count=len(categories))
