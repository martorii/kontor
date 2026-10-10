import streamlit as st

st.set_page_config(page_title="Kontor", page_icon="💶", layout="wide")

navigation = st.navigation(
    [
        st.Page("pages/monthly.py", title="Monthly overview", icon="📅", default=True),
        st.Page("pages/ask.py", title="Ask", icon="💬"),
        st.Page("pages/year.py", title="Year comparison", icon="📊"),
        st.Page("pages/merchants.py", title="Top merchants", icon="🏪"),
        st.Page("pages/review.py", title="Review", icon="📝"),
        st.Page("pages/explorer.py", title="Transaction explorer", icon="🔎"),
        st.Page("pages/upload.py", title="Upload", icon="⬆️"),
        st.Page("pages/rerun_llm.py", title="Re-run LLM", icon="🤖"),
        st.Page("pages/imports.py", title="Import history", icon="🕘"),
        st.Page("pages/accounts.py", title="Accounts", icon="🏦"),
    ]
)
navigation.run()
