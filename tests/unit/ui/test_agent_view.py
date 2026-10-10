from typing import Any

import pytest

from agent_view import chart_data, matched_no_data


def response(chart: dict[str, Any], rows: list[list[Any]]) -> dict[str, Any]:
    return {"columns": ["month", "spent", "note"], "rows": rows, "chart": chart}


ROWS = [["2026-01", "120.50", "a"], ["2026-02", "-3.10", "b"]]


@pytest.mark.parametrize("kind", ["bar", "line"])
def test_money_strings_become_numbers_for_the_chart(kind: str) -> None:
    data = chart_data(response({"type": kind, "x": "month", "y": "spent"}, ROWS))

    assert data == {"month": ["2026-01", "2026-02"], "spent": [120.5, -3.1]}


def test_int_and_float_values_are_used_as_they_are() -> None:
    rows = [["a", 3, None], ["b", 0.5, None]]

    data = chart_data(response({"type": "bar", "x": "month", "y": "spent"}, rows))

    assert data == {"month": ["a", "b"], "spent": [3.0, 0.5]}


def test_no_chart_type_gives_none() -> None:
    assert chart_data(response({"type": "none", "x": None, "y": None}, ROWS)) is None


def test_missing_chart_gives_none() -> None:
    assert chart_data({"columns": [], "rows": []}) is None


def test_unknown_columns_give_none() -> None:
    assert chart_data(response({"type": "bar", "x": "month", "y": "nope"}, ROWS)) is None


def test_unconvertible_values_give_none() -> None:
    assert chart_data(response({"type": "bar", "x": "month", "y": "note"}, ROWS)) is None


def test_booleans_are_not_numbers() -> None:
    rows: list[list[Any]] = [["a", True, None]]

    assert chart_data(response({"type": "bar", "x": "month", "y": "spent"}, rows)) is None


def test_null_values_are_left_out() -> None:
    rows: list[list[Any]] = [["2026-01", None, "a"], ["2026-02", "5.00", "b"]]

    data = chart_data(response({"type": "line", "x": "month", "y": "spent"}, rows))

    assert data == {"month": ["2026-02"], "spent": [5.0]}


def test_only_nulls_give_none() -> None:
    rows = [["2026-01", None, "a"]]

    assert chart_data(response({"type": "bar", "x": "month", "y": "spent"}, rows)) is None


def answered(rows: list[list[Any]]) -> dict[str, Any]:
    return {"status": "answered", "columns": ["avg"], "rows": rows}


def test_no_rows_matched_no_data() -> None:
    assert matched_no_data(answered([])) is True


def test_only_nulls_matched_no_data() -> None:
    """AVG over zero matching rows returns one row holding NULL."""
    assert matched_no_data(answered([[None]])) is True
    assert matched_no_data(answered([[None], [None]])) is True


def test_any_value_is_data() -> None:
    assert matched_no_data(answered([[None], ["12.50"]])) is False
    assert matched_no_data(answered([[0]])) is False


def test_gave_up_is_not_an_empty_result() -> None:
    assert matched_no_data({"status": "gave_up", "columns": [], "rows": []}) is False
