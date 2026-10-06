import streamlit as st

from api_client import ApiClient
from report_common import (
    account_select,
    chart_number,
    load,
    money,
    percent,
    provisional_notice,
    year_select,
)

api = ApiClient.from_env()

st.title("Year comparison")

left, right = st.columns(2)
with left:
    year = year_select()
with right:
    account_id = account_select(api)

report = load(lambda: api.year_report(year, account_id))
currency = report["currency"]
if currency is None:
    st.info("No transactions for these years.")
    st.stop()

provisional_notice(report)
previous_year = report["previous_year"]
first, second, third = st.columns(3)
first.metric(str(year), money(report["total"], currency))
second.metric(str(previous_year), money(report["previous_total"], currency))
third.metric("Change", money(report["change"], currency))

categories = report["categories"]
st.bar_chart(
    {
        "Category": [c["name"] for c in categories],
        str(previous_year): [chart_number(c["previous_total"]) for c in categories],
        str(year): [chart_number(c["total"]) for c in categories],
    },
    x="Category",
    y=[str(previous_year), str(year)],
    stack=False,
)
st.dataframe(
    [
        {
            "Category": c["name"],
            str(year): money(c["total"], currency),
            str(previous_year): money(c["previous_total"], currency),
            "Change": money(c["change"], currency),
            "Change %": percent(c["change_ratio"]),
        }
        for c in categories
    ],
    hide_index=True,
    use_container_width=True,
)
