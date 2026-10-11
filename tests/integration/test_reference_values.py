from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy import Engine, text

from kontor.adapters.db.reference_values import PostgresReferenceValues
from kontor.agent_eval_seed import seed
from kontor.domain.reference import CategoryRef


@pytest.fixture
def seeded(engine: Engine) -> Iterator[None]:
    seed(engine, date(2026, 10, 10))
    yield
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE categorization_events, transactions, imports, accounts, categories "
                "RESTART IDENTITY CASCADE"
            )
        )


def test_loads_the_category_tree_and_account_names(engine: Engine, seeded: None) -> None:
    values = PostgresReferenceValues(engine).load()

    assert CategoryRef("food", "Food", None, "expense") in values.categories
    assert CategoryRef("food.groceries", "Groceries", "food", None) in values.categories
    assert values.accounts == ("Gemeinschaftskonto", "Girokonto")
