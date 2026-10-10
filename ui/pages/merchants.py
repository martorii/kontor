import streamlit as st

from api_client import ApiClient
from report_common import account_select, chart_number, load, money, month_select, year_select

api = ApiClient.from_env()

st.title("Top merchants")

first, second, third, fourth = st.columns(4)
with first:
    year = year_select()
with second:
    month = month_select(allow_all=True)
with third:
    account_id = account_select(api)
with fourth:
    limit = int(st.number_input("Show", min_value=1, max_value=100, value=10))

report = load(lambda: api.top_merchants_report(year, month, account_id, limit))
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
