from datetime import date

import streamlit as st

from api_client import ApiClient, ApiError, ApiUnreachableError
from report_common import accounts_multiselect, chart_number, load, money

UNCATEGORIZED = "uncategorized"

api = ApiClient.from_env()


def subcategories_by_parent() -> dict[str, dict[str, str]]:
    """Top-level slug → {subcategory slug: name}. Stops the page on error."""
    try:
        categories = api.list_categories()
    except (ApiError, ApiUnreachableError) as exc:
        st.error(str(exc))
        st.stop()
    tree: dict[str, dict[str, str]] = {}
    for c in categories:
        tree.setdefault(c["parent_slug"], {})[c["slug"]] = c["name"]
    return dict(sorted(tree.items()))


st.title("Top merchants")

first, second, third = st.columns([2, 2, 1])
with first:
    account_ids = accounts_multiselect(api)
bounds = load(lambda: api.date_bounds(account_ids))
if bounds["first"] is None:
    st.info("No transactions yet.")
    st.stop()
available_from = date.fromisoformat(bounds["first"])
available_to = date.fromisoformat(bounds["last"])
with second:
    # The key follows the bounds, so the range resets to the full span when the accounts change.
    picked = st.date_input(
        "Date range",
        value=(available_from, available_to),
        min_value=available_from,
        max_value=available_to,
        key=f"merchants-range-{available_from}-{available_to}",
    )
with third:
    limit = int(st.number_input("Show", min_value=1, max_value=100, value=10))

tree = subcategories_by_parent()
fourth, fifth, _ = st.columns([2, 2, 1])
with fourth:
    parent = st.selectbox(
        "Category",
        [None, *tree, UNCATEGORIZED],
        format_func=lambda slug: {None: "All", UNCATEGORIZED: "Uncategorized"}.get(slug, slug),
    )
subcategories = tree.get(parent or "", {})
with fifth:
    # The key follows the category, so the subcategory resets to "All" when it changes.
    subcategory = st.selectbox(
        "Subcategory",
        [None, *subcategories],
        format_func=lambda slug: "All" if slug is None else subcategories[slug],
        disabled=not subcategories,
        key=f"merchants-subcategory-{parent}",
    )
# A top-level slug includes its subcategories (CONTRACT §11.1b).
category = subcategory or parent

if not isinstance(picked, tuple) or len(picked) != 2:
    st.info("Pick an end date to complete the range.")
    st.stop()
date_from, date_to = picked

report = load(lambda: api.top_merchants_report(date_from, date_to, account_ids, limit, category))
currency = report["currency"]
merchants = report["merchants"]
if currency is None or not merchants:
    st.info("No merchant spending for this period.")
    st.stop()

st.bar_chart(
    {
        "Merchant": [m["merchant"] for m in merchants],
        "Spent": [chart_number(m["total"]) for m in merchants],
    },
    x="Merchant",
    y="Spent",
    horizontal=True,
    sort="-Spent",
)
st.dataframe(
    [
        {
            "Merchant": m["merchant"],
            "Spent": money(m["total"], currency),
            "Transactions": m["transaction_count"],
        }
        for m in merchants
    ],
    hide_index=True,
    use_container_width=True,
)
