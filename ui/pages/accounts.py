import streamlit as st

from api_client import ApiClient, ApiError, ApiUnreachableError

api = ApiClient.from_env()

st.title("Accounts")

try:
    accounts = api.list_accounts()
except (ApiError, ApiUnreachableError) as exc:
    st.error(str(exc))
    st.stop()

if not accounts:
    st.info("No accounts yet. An account is created by the first upload.")

EDITABLE = {
    "name": "Name",
    "bank": "Bank",
    "iban": "IBAN",
    "currency": "Currency",
    "account_type": "Account type",
    "parser_format": "Parser format",
}

for account in accounts:
    title = f"{account['name']} ({account['iban']})"
    with st.expander(title, expanded=len(accounts) == 1), st.form(f"account-{account['id']}"):
        values = {
            field: st.text_input(label, value=account[field], key=f"{field}-{account['id']}")
            for field, label in EDITABLE.items()
        }
        if st.form_submit_button("Save"):
            changes = {f: v for f, v in values.items() if v != account[f]}
            if not changes:
                st.info("Nothing changed.")
            else:
                try:
                    api.update_account(account["id"], changes)
                except ApiError as exc:
                    st.error(f"Could not save: {exc.detail}")
                except ApiUnreachableError as exc:
                    st.error(str(exc))
                else:
                    st.success("Saved.")
                    st.rerun()
