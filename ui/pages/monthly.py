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
    {c["name"]: chart_number(c["total"]) for c in categories},
    horizontal=True,
)

st.subheader("By category")
st.caption("Open a category to see its subcategories and pick one to list its transactions.")

first_day = date(year, month, 1)
last_day = date(year, month, calendar.monthrange(year, month)[1])
LIMIT = 500


try:
    assignable = {c["slug"]: f"{c['parent_slug']} › {c['name']}" for c in api.list_categories()}
except (ApiError, ApiUnreachableError) as exc:
    st.error(str(exc))
    st.stop()


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
    items = page["items"]
    key = f"tx-{category['slug']}-{sub_slug}"
    event = st.dataframe(
        [
            {
                "Date": t["booking_date"],
                "Reference": t["counterparty"],
                "Amount": money(t["amount"], t["currency"]),
                "Category": assignable.get(t["category"], t["category"] or "–"),
                "Set by": t["category_source"] or "–",
            }
            for t in items
        ],
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        key=key,
    )
    if page["total"] > LIMIT:
        st.caption(f"Showing the first {LIMIT} of {page['total']} transactions.")
    selected = event.selection.rows
    if not selected:
        st.caption("Select a transaction to change its category.")
        return
    transaction = items[selected[0]]
    st.markdown(f"**{transaction['counterparty']}** — change category")
    options = list(assignable)
    current = transaction["category"]
    target = st.selectbox(
        "New category",
        options,
        index=options.index(current) if current in options else None,
        format_func=lambda slug: assignable[slug],
        placeholder="Choose a category",
        key=f"{key}-target",
    )
    if st.button("Save category", key=f"{key}-save", disabled=target is None):
        try:
            api.set_category(transaction["transaction_id"], str(target))
        except (ApiError, ApiUnreachableError) as exc:
            st.error(str(exc))
        else:
            st.rerun()


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
