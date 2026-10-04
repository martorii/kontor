from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from kontor.adapters.db.uow import SqlUnitOfWork
from kontor.api.app import create_app
from kontor.application.category_sync import sync_categories
from kontor.config import Settings
from kontor.domain.rules import CategoryDef

ROOT = Path(__file__).resolve().parents[2]

TREE = (
    CategoryDef("food", "Food", None, "expense"),
    CategoryDef("food.groceries", "Groceries", "food", None),
    CategoryDef("income", "Income", None, "income"),
)


@pytest.fixture
def uow_factory(engine: Engine) -> Iterator["sessionmaker[Session]"]:
    yield sessionmaker(engine)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE categories CASCADE"))


def rows(engine: Engine) -> list[tuple[str, str | None, str, str | None]]:
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT slug, parent_slug, name, kind FROM categories ORDER BY slug")
        )
        return [tuple(r) for r in result]


def test_sync_is_idempotent(engine: Engine, uow_factory: "sessionmaker[Session]") -> None:
    def factory() -> SqlUnitOfWork:
        return SqlUnitOfWork(uow_factory)

    sync_categories(factory, TREE)
    first = rows(engine)
    sync_categories(factory, TREE)

    assert rows(engine) == first
    assert first == [
        ("food", None, "Food", "expense"),
        ("food.groceries", "food", "Groceries", None),
        ("income", None, "Income", "income"),
    ]


def test_sync_updates_changed_names_and_keeps_removed_categories(
    engine: Engine, uow_factory: "sessionmaker[Session]"
) -> None:
    def factory() -> SqlUnitOfWork:
        return SqlUnitOfWork(uow_factory)

    sync_categories(factory, TREE)
    sync_categories(factory, (CategoryDef("food", "Groceries & food", None, "expense"),))

    by_slug = {r[0]: r for r in rows(engine)}
    assert by_slug["food"][2] == "Groceries & food"
    assert "food.groceries" in by_slug  # transactions may reference it, so it is never deleted


def test_app_startup_syncs_the_example_tree(
    engine: Engine, postgres_url: str, uow_factory: "sessionmaker[Session]"
) -> None:
    settings = Settings(
        database_url=postgres_url, rules_path=str(ROOT / "config" / "rules.example.yaml")
    )

    with TestClient(create_app(settings)):
        first = rows(engine)
    with TestClient(create_app(settings)):
        assert rows(engine) == first

    slugs = {r[0] for r in first}
    assert {"kids.daycare", "food.groceries", "income.salary"} <= slugs


def test_app_startup_fails_fast_on_invalid_rules(tmp_path: Path, postgres_url: str) -> None:
    bad = tmp_path / "rules.yaml"
    bad.write_text("categories: [broken\n")

    with (
        pytest.raises(Exception, match="invalid YAML"),
        TestClient(create_app(Settings(database_url=postgres_url, rules_path=str(bad)))),
    ):
        pass
