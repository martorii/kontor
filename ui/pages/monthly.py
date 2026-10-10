import calendar
from datetime import date
from typing import Any  # Any: JSON bodies are untyped by nature

import streamlit as st

from api_client import ApiClient, ApiError, ApiUnreachableError
from report_common import (
    account_select,
    chart_number,
    load,
    money,
    month_select,
    provisional_notice,
    year_select,
)
from transaction_table import assignable_categories, transaction_table

api = ApiClient.from_env()

st.title("Monthly overview")

left, middle, right = st.columns(3)
with left:
    year = year_select()
with middle:
    month = month_select() or 1
with right:
    account_id = account_select(api)

report = load(lambda: api.monthly_report(year, month, account_id))
currency = report["currency"]
if currency is None:
    st.info("No transactions for this month.")
    st.stop()

provisional_notice(report)
st.metric("Total spending", money(report["total"], currency))

categories = report["categories"]
st.bar_chart(
    {
        "Category": [c["name"] for c in categories],
        "Spent": [chart_number(c["total"]) for c in categories],
    },
    x="Category",
    y="Spent",
    horizontal=True,
    sort="-Spent",
)

st.subheader("By category")
st.caption("Open a category to see its subcategories and pick one to list its transactions.")

first_day = date(year, month, 1)
last_day = date(year, month, calendar.monthrange(year, month)[1])
LIMIT = 500


assignable = assignable_categories(api)


def show_transactions(category: dict[str, Any], sub_slug: str | None) -> None:
    filters: dict[str, str | int | None] = {
        "account_id": account_id,
        "date_from": first_day.isoformat(),
        "date_to": last_day.isoformat(),
        "limit": LIMIT,
    }
    if category["uncategorized"]:
        filters["source"] = "none"
    else:
        filters["category"] = sub_slug or category["slug"]
    try:
        page = api.transactions(**filters)
    except (ApiError, ApiUnreachableError) as exc:
        st.error(str(exc))
        return
    key = f"tx-{category['slug']}-{sub_slug}"
    transaction_table(api, page["items"], assignable, key)
    if page["total"] > LIMIT:
        st.caption(f"Showing the first {LIMIT} of {page['total']} transactions.")


for category in categories:
    label = f"{category['name']} — {money(category['total'], currency)}"
    with st.expander(label):
        subcategories = category["subcategories"]
        st.dataframe(
            [
                {
                    "Subcategory": sub["name"],
                    "Total": money(sub["total"], currency),
                    "Transactions": sub["transaction_count"],
                }
                for sub in subcategories
            ],
            hide_index=True,
            use_container_width=True,
        )
        names = {sub["slug"]: sub["name"] for sub in subcategories}
        options: list[str | None] = [None, *names]

        def option_label(
            slug: str | None, names: dict[str, str] = names, name: str = category["name"]
        ) -> str:
            return f"All of {name}" if slug is None else names[slug]

        choice = st.selectbox(
            "Transactions of", options, format_func=option_label, key=f"sub-{category['slug']}"
        )
        show_transactions(category, choice)
