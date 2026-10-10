"""The database layer of the agent's safety model (CONTRACT §16.3), without the validator."""

from collections.abc import Iterator
from decimal import Decimal

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from kontor.adapters.db.query_executor import PostgresQueryExecutor
from kontor.domain.errors import QueryExecutionError, QueryTimeoutError


@pytest.fixture
def executor(engine: Engine) -> PostgresQueryExecutor:
    return PostgresQueryExecutor(engine, timeout_seconds=1.0, max_rows=500)


@pytest.fixture
def account_id(engine: Engine) -> Iterator[int]:
    """One committed account, so writes have something to hit. Removed afterwards."""
    with engine.begin() as conn:
        new_id: int = conn.execute(
            text(
                "INSERT INTO accounts (name, bank, iban, currency, account_type, parser_format) "
                "VALUES ('Test account', 'Testbank', 'DE00000000000000000000', 'EUR', "
                "'checking', 'test') RETURNING id"
            )
        ).scalar_one()
    yield new_id
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE accounts RESTART IDENTITY CASCADE"))


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO accounts (name, bank, iban, currency, account_type, parser_format) "
        "VALUES ('x', 'x', 'DE11111111111111111111', 'EUR', 'checking', 'test')",
        "UPDATE accounts SET name = 'changed'",
        "DELETE FROM accounts",
        "CREATE TABLE agent_scratch (id int)",
        "DROP VIEW v_flows",
    ],
)
def test_writes_are_rejected_and_change_nothing(
    executor: PostgresQueryExecutor, engine: Engine, account_id: int, sql: str
) -> None:
    with pytest.raises(QueryExecutionError):
        executor.execute(sql)

    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, name FROM accounts")).all()
        view = conn.execute(text("SELECT to_regclass('v_flows')")).scalar_one()
        scratch = conn.execute(text("SELECT to_regclass('agent_scratch')")).scalar_one()
    assert [tuple(row) for row in rows] == [(account_id, "Test account")]
    assert view is not None
    assert scratch is None


def test_writes_are_rejected_by_the_role_alone(engine: Engine, account_id: int) -> None:
    """Without the read-only transaction, the role's missing privileges still block a write."""
    with engine.connect() as conn, conn.begin() as transaction:
        conn.execute(text("SET LOCAL ROLE kontor_agent"))
        with pytest.raises(DBAPIError, match="permission denied"):
            conn.execute(text("UPDATE accounts SET name = 'changed'"))
        transaction.rollback()


def test_alembic_version_is_not_readable(executor: PostgresQueryExecutor) -> None:
    with pytest.raises(QueryExecutionError, match="permission denied"):
        executor.execute("SELECT * FROM alembic_version")


def test_tables_and_views_are_readable(executor: PostgresQueryExecutor, account_id: int) -> None:
    accounts = executor.execute("SELECT id, name FROM accounts")
    flows = executor.execute("SELECT * FROM v_flows")

    assert accounts.columns == ("id", "name")
    assert accounts.rows == ((account_id, "Test account"),)
    assert flows.rows == ()


def test_long_query_hits_the_timeout(executor: PostgresQueryExecutor) -> None:
    with pytest.raises(QueryTimeoutError):
        executor.execute("SELECT pg_sleep(20)")


def test_result_over_the_cap_is_truncated(executor: PostgresQueryExecutor) -> None:
    result = executor.execute("SELECT n FROM generate_series(1, 1000) AS n")

    assert len(result.rows) == 500
    assert result.rows[-1] == (500,)
    assert result.truncated is True


def test_result_at_the_cap_is_not_truncated(executor: PostgresQueryExecutor) -> None:
    result = executor.execute("SELECT n FROM generate_series(1, 500) AS n")

    assert len(result.rows) == 500
    assert result.truncated is False


def test_numeric_comes_back_as_decimal(executor: PostgresQueryExecutor) -> None:
    result = executor.execute("SELECT -12.34::numeric(12, 2) AS amount")

    assert result.rows == ((Decimal("-12.34"),),)
    assert isinstance(result.rows[0][0], Decimal)


def test_sql_text_is_passed_through_unchanged(executor: PostgresQueryExecutor) -> None:
    """`%` and `:name` in the SQL are not treated as bind parameters."""
    result = executor.execute("SELECT 'a:b' AS x WHERE 'abc' LIKE '%b%'")

    assert result.rows == (("a:b",),)


def test_role_does_not_leak_into_the_next_query(
    executor: PostgresQueryExecutor, engine: Engine
) -> None:
    executor.execute("SELECT 1")

    with engine.connect() as conn:
        role = conn.execute(text("SELECT current_user")).scalar_one()
    assert role != "kontor_agent"
