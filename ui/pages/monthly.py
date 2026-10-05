import streamlit as st

from api_client import ApiClient
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
for category in categories:
    label = f"{category['name']} — {money(category['total'], currency)}"
    with st.expander(label):
        st.dataframe(
            [
                {
                    "Subcategory": sub["name"],
                    "Total": money(sub["total"], currency),
                    "Transactions": sub["transaction_count"],
                }
                for sub in category["subcategories"]
            ],
            hide_index=True,
            use_container_width=True,
        )
