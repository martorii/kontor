import psycopg.errors
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from kontor.domain.errors import QueryExecutionError, QueryTimeoutError
from kontor.domain.query import QueryResult

# Created by the agent role migration; SELECT only (CONTRACT §16.3).
AGENT_ROLE = "kontor_agent"


class PostgresQueryExecutor:
    """Runs agent SQL in a read-only transaction, as `kontor_agent`, and always rolls back."""

    def __init__(self, engine: Engine, timeout_seconds: float, max_rows: int) -> None:
        self._engine = engine
        self._timeout_ms = str(int(timeout_seconds * 1000))
        self._max_rows = max_rows

    def execute(self, sql: str) -> QueryResult:
        with self._engine.connect() as conn:
            transaction = conn.begin()
            try:
                conn.execute(text("SET TRANSACTION READ ONLY"))
                conn.execute(text(f"SET LOCAL ROLE {AGENT_ROLE}"))
                conn.execute(
                    text("SELECT set_config('statement_timeout', :ms, true)"),
                    {"ms": self._timeout_ms},
                )
                try:
                    # Pass the text to the driver as is: no `:name` binds, and with
                    # no_parameters psycopg does not read `%` as a placeholder.
                    result = conn.execution_options(no_parameters=True).exec_driver_sql(sql)
                    if not result.returns_rows:
                        return QueryResult(columns=(), rows=(), truncated=False)
                    columns = tuple(result.keys())
                    fetched = result.fetchmany(self._max_rows + 1)
                except DBAPIError as exc:
                    if isinstance(exc.orig, psycopg.errors.QueryCanceled):
                        raise QueryTimeoutError(str(exc.orig)) from exc
                    raise QueryExecutionError(str(exc.orig)) from exc
            finally:
                transaction.rollback()
        return QueryResult(
            columns=columns,
            rows=tuple(tuple(row) for row in fetched[: self._max_rows]),
            truncated=len(fetched) > self._max_rows,
        )
