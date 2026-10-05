import streamlit as st

st.set_page_config(page_title="Kontor", page_icon="💶", layout="wide")

navigation = st.navigation(
    [
        st.Page("pages/upload.py", title="Upload", icon="⬆️", default=True),
        st.Page("pages/imports.py", title="Import history", icon="🕘"),
        st.Page("pages/accounts.py", title="Accounts", icon="🏦"),
    ]
)
navigation.run()
