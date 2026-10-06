from datetime import date

import streamlit as st

from api_client import ApiClient, ApiError, ApiUnreachableError
from report_common import account_select
from transaction_table import assignable_categories, transaction_table

api = ApiClient.from_env()
PAGE_SIZE = 100
SOURCES = {
    None: "Any",
    "rule": "Rule",
    "llm": "LLM",
    "manual": "Manual",
    "none": "Uncategorized",
}

st.title("Transaction explorer")
assignable = assignable_categories(api)
# A top-level slug includes its subcategories (CONTRACT §11.1a).
parents = sorted({slug.split(".")[0] for slug in assignable})
category_options: list[str | None] = [None, *parents, *assignable]


def category_label(slug: str | None) -> str:
    if slug is None:
        return "Any"
    return assignable.get(slug, f"{slug} (all)")


first, second, third = st.columns(3)
with first:
    account_id = account_select(api)
with second:
    date_from = st.date_input("From", value=None, max_value=date.today())
with third:
    date_to = st.date_input("To", value=None, max_value=date.today())
fourth, fifth, sixth = st.columns(3)
with fourth:
    category = st.selectbox("Category", category_options, format_func=category_label)
with fifth:
    source = st.selectbox("Set by", list(SOURCES), format_func=lambda s: SOURCES[s])
with sixth:
    text = st.text_input("Counterparty or purpose contains")

# The page is reset when a filter changes, so a stale offset never lands past the end.
filters = (account_id, date_from, date_to, category, source, text)
if st.session_state.get("explorer_filters") != filters:
    st.session_state["explorer_filters"] = filters
    st.session_state["explorer_page"] = 1

try:
    page_number = int(st.session_state.get("explorer_page", 1))
    page = api.transactions(
        account_id=account_id,
        date_from=date_from.isoformat() if date_from else None,
        date_to=date_to.isoformat() if date_to else None,
        category=category,
        source=source,
        q=text or None,
        limit=PAGE_SIZE,
        offset=(page_number - 1) * PAGE_SIZE,
    )
except (ApiError, ApiUnreachableError) as exc:
    st.error(str(exc))
    st.stop()

total_pages = max(1, -(-page["total"] // PAGE_SIZE))
st.caption(f"{page['total']} transactions")
if total_pages > 1:
    st.number_input("Page", min_value=1, max_value=total_pages, step=1, key="explorer_page")
if not page["items"]:
    st.info("No transactions match these filters.")
else:
    transaction_table(api, page["items"], assignable, "explorer")
