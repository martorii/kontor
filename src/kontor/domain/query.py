from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class QueryResult:
    """The outcome of one agent query (CONTRACT §16.3).

    Values keep their Python types (`Decimal`, `date`, ...); JSON conversion happens in the API.
    `truncated` is True when the query had more rows than the row cap.
    """

    columns: tuple[str, ...]
    rows: tuple[tuple[object, ...], ...]
    truncated: bool
