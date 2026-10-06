import streamlit as st

from api_client import ApiClient
from report_common import (
    MONTHS,
    account_select,
    chart_number,
    load,
    money,
    percent,
    provisional_notice,
    year_select,
)

api = ApiClient.from_env()

st.title("Income vs. expenses")

left, right = st.columns(2)
with left:
    year = year_select()
with right:
    account_id = account_select(api)

report = load(lambda: api.income_expenses_report(year, account_id))
currency = report["currency"]
if currency is None:
    st.info("No transactions for this year.")
    st.stop()

provisional_notice(report)
first, second, third, fourth = st.columns(4)
first.metric("Income", money(report["income"], currency))
second.metric("Expenses", money(report["expenses"], currency))
third.metric("Net", money(report["net"], currency))
fourth.metric("Savings rate", percent(report["savings_rate"]))

months = report["months"]
st.bar_chart(
    {
        "Month": [MONTHS[m["month"] - 1][:3] for m in months],
        "Month no.": [m["month"] for m in months],
        "Income": [chart_number(m["income"]) for m in months],
        "Expenses": [chart_number(m["expenses"]) for m in months],
    },
    x="Month",
    y=["Income", "Expenses"],
    stack=False,
    sort="Month no.",  # calendar order, not alphabetical
)
st.dataframe(
    [
        {
            "Month": MONTHS[m["month"] - 1],
            "Income": money(m["income"], currency),
            "Expenses": money(m["expenses"], currency),
            "Net": money(m["net"], currency),
            "Savings rate": percent(m["savings_rate"]),
        }
        for m in months
    ],
    hide_index=True,
    use_container_width=True,
)
