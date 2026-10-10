"""The golden set against the synthetic seed: every reference query runs as the agent role."""

from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy import Engine, text

from kontor.adapters.db.query_executor import PostgresQueryExecutor
from kontor.agent_eval_cli import DEFAULT_GOLDEN, has_tables, load_golden, run
from kontor.agent_eval_seed import generate, seed
from kontor.application.agent_evaluation import is_empty
from kontor.config import Settings


@pytest.fixture
def seeded(engine: Engine) -> Iterator[int]:
    count = seed(engine, date.today())
    yield count
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE categorization_events, transactions, imports, accounts, categories "
                "RESTART IDENTITY CASCADE"
            )
        )


def test_seed_is_deterministic_and_never_in_the_future() -> None:
    today = date(2026, 10, 10)

    rows = generate(today)

    assert rows == generate(today)
    assert len(rows) > 300
    assert max(row.booking_date for row in rows) <= today
    assert min(row.booking_date for row in rows) == date(2025, 10, 1)


def test_every_reference_query_runs_as_the_agent_role(engine: Engine, seeded: int) -> None:
    executor = PostgresQueryExecutor(engine, timeout_seconds=10, max_rows=500)

    empty = [
        item.id
        for item in load_golden(DEFAULT_GOLDEN)
        if is_empty(executor.execute(item.reference_sql))
    ]

    assert seeded > 300
    # Early in the year some "this year" questions have no data yet (the first clothing
    # refund is on 25 March), so only check for data from April on.
    if date.today() >= date(date.today().year, 4, 1):
        assert empty == []


def test_eval_refuses_a_database_that_has_tables(
    engine: Engine, postgres_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = Settings(
        database_url=postgres_url, agent_llm_base_url="http://llm.test/v1", agent_llm_model="m"
    )

    assert has_tables(engine)
    assert run(DEFAULT_GOLDEN, settings) == 1
    assert "empty scratch database" in capsys.readouterr().err
