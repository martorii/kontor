from typing import Protocol

from kontor.domain.query import QueryResult


class QueryExecutor(Protocol):
    def execute(self, sql: str) -> QueryResult:
        """Run `sql` read-only, under the agent role, with the timeout and row cap.

        Raises QueryTimeoutError or QueryExecutionError.
        """
        ...
