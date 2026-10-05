"""Shared controls and formatting for the report pages. No aggregation happens here."""

from datetime import date
from decimal import Decimal
from typing import Any  # Any: JSON bodies are untyped by nature

import streamlit as st

from api_client import ApiClient, ApiError, ApiUnreachableError

MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


def money(value: str | None, currency: str | None) -> str:
    """Format an API amount (a decimal string) for display."""
    if value is None:
        return "–"
    return f"{Decimal(value):,.2f} {currency or ''}".strip()


def percent(value: str | None) -> str:
    return "–" if value is None else f"{Decimal(value) * 100:.1f} %"


def chart_number(value: str) -> float:
    # float: only feeds the chart renderer; displayed figures use Decimal via money().
    return float(Decimal(value))


def account_select(api: ApiClient) -> int | None:
    """Sidebar-free account picker. Returns None for all accounts."""
    try:
        accounts = api.list_accounts()
    except (ApiError, ApiUnreachableError) as exc:
        st.error(str(exc))
        st.stop()
    names = {a["id"]: f"{a['name']} ({a['iban']})" for a in accounts}
    choice: int | None = st.selectbox(
        "Account", [None, *names], format_func=lambda i: "All accounts" if i is None else names[i]
    )
    return choice


def year_select(key: str = "year") -> int:
    this_year = date.today().year
    return int(
        st.selectbox("Year", list(range(this_year, this_year - 10, -1)), key=key) or this_year
    )


def month_select(*, allow_all: bool = False, key: str = "month") -> int | None:
    options: list[int | None] = list(range(1, 13))
    index = date.today().month - 1
    if allow_all:
        options = [None, *options]
        index += 1
    return st.selectbox(
        "Month",
        options,
        index=index,
        format_func=lambda m: "Whole year" if m is None else MONTHS[m - 1],
        key=key,
    )


def provisional_notice(report: dict[str, Any]) -> None:
    if report.get("includes_uncategorized"):
        st.warning("Provisional: uncategorized transactions are counted in these totals.")


def load(report_call: Any) -> dict[str, Any]:  # Any: a zero-argument callable
    """Run an API call; show the error and stop the page when it fails."""
    try:
        return report_call()  # type: ignore[no-any-return]
    except (ApiError, ApiUnreachableError) as exc:
        st.error(exc.detail if isinstance(exc, ApiError) else str(exc))
        st.stop()
