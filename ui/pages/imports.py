import streamlit as st

from api_client import ApiClient, ApiError, ApiUnreachableError

api = ApiClient.from_env()

st.title("Import history")

try:
    imports = api.list_imports()
    accounts = {a["id"]: a["name"] for a in api.list_accounts()}
except (ApiError, ApiUnreachableError) as exc:
    st.error(str(exc))
else:
    if not imports:
        st.info("No imports yet.")
    else:
        st.dataframe(
            [
                {
                    "Imported at": i["created_at"],
                    "File": i["file_name"],
                    "Account": accounts.get(i["account_id"], i["account_id"]),
                    "Status": i["status"],
                    "New": i["new_count"],
                    "Duplicates": i["duplicate_count"],
                    "Rules": i["rule_matched_count"],
                    "LLM": i["llm_matched_count"],
                    "Uncategorized": i["uncategorized_count"],
                }
                for i in imports
            ],
            hide_index=True,
            use_container_width=True,
        )
