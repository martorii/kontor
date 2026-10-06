"""A transaction table with in-place re-labelling, shared by the report drill-down and explorer."""

from typing import Any  # Any: JSON bodies are untyped by nature

import streamlit as st

from api_client import ApiClient, ApiError, ApiUnreachableError
from report_common import money


def assignable_categories(api: ApiClient) -> dict[str, str]:
    """Slug → label for every category a transaction can be assigned to. Stops the page on error."""
    try:
        return {c["slug"]: f"{c['parent_slug']} › {c['name']}" for c in api.list_categories()}
    except (ApiError, ApiUnreachableError) as exc:
        st.error(str(exc))
        st.stop()


def category_picker(
    api: ApiClient, transaction: dict[str, Any], assignable: dict[str, str], key: str
) -> None:
    """Pick a category for one transaction and save it as a manual categorization."""
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


def transaction_table(
    api: ApiClient, items: list[dict[str, Any]], assignable: dict[str, str], key: str
) -> None:
    """Show explorer items; selecting a row offers a category change."""
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
    selected = event.selection.rows
    if not selected:
        st.caption("Select a transaction to change its category.")
        return
    transaction = items[selected[0]]
    st.markdown(f"**{transaction['counterparty']}** — change category")
    category_picker(api, transaction, assignable, key)
