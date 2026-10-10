import streamlit as st

from api_client import ApiClient, ApiError, ApiTimeoutError, ApiUnreachableError
from progress import run_with_llm_progress

api = ApiClient.from_env()

st.title("Upload")
st.caption("Import a bank CSV export. Duplicates are skipped; the new rows are categorized.")

uploaded = st.file_uploader("Bank export (CSV)", type=["csv"])
if uploaded is not None and st.button("Import", type="primary"):
    file_name, content = uploaded.name, uploaded.getvalue()
    try:
        result = run_with_llm_progress(
            api,
            lambda: api.upload_import(file_name, content),
            "Parsing the file and applying the rules...",
        )
    except ApiError as exc:
        st.error(f"Import failed: {exc.detail}")
    except ApiTimeoutError as exc:
        st.warning(
            f"{exc} The import may still be running on the API, because the LLM step can take "
            "a long time. Check **Import history** before uploading the file again."
        )
    except ApiUnreachableError as exc:
        st.error(str(exc))
    else:
        if result["account_created"]:
            st.info(
                f"A new account was created (id {result['account_id']}). "
                "You can rename it under Accounts."
            )
        st.success(f"Imported {result['file_name']}")
        columns = st.columns(5)
        columns[0].metric("New", result["new_count"])
        columns[1].metric("Duplicates", result["duplicate_count"])
        columns[2].metric("By rules", result["rule_matched_count"])
        columns[3].metric("By LLM", result["llm_matched_count"])
        columns[4].metric("Uncategorized", result["uncategorized_count"])
