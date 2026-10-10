"""Turns an agent answer's chart spec into chart data. No Streamlit, so it can be tested."""

from decimal import Decimal, InvalidOperation
from typing import Any  # Any: JSON bodies are untyped by nature


def chart_data(response: dict[str, Any]) -> dict[str, list[Any]] | None:
    """The `x` and `y` columns for st.bar_chart / st.line_chart, or None for no chart.

    The API already checked the spec against the result (CONTRACT §16.6); this only maps it.
    Money arrives as strings and becomes float here, for the chart only: the table keeps the
    exact strings. Rows with a null `y` are left out. Anything unexpected means no chart.
    """
    chart = response.get("chart") or {}
    if chart.get("type") not in ("bar", "line"):
        return None
    columns: list[str] = response.get("columns") or []
    x, y = chart.get("x"), chart.get("y")
    if x not in columns or y not in columns:
        return None
    x_index, y_index = columns.index(x), columns.index(y)
    xs: list[Any] = []
    ys: list[float] = []
    for row in response.get("rows") or []:
        if row[y_index] is None:
            continue
        number = _number(row[y_index])
        if number is None:
            return None
        xs.append(row[x_index])
        ys.append(number)
    if not ys:
        return None
    return {x: xs, y: ys}


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            # float: only feeds the chart renderer; the table shows the exact string.
            return float(Decimal(value))
        except InvalidOperation:
            return None
    return None
