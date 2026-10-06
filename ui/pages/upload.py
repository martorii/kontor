import threading
import time
from typing import Any  # Any: JSON bodies are untyped by nature

import streamlit as st

from api_client import ApiClient, ApiError, ApiTimeoutError, ApiUnreachableError

api = ApiClient.from_env()

st.title("Upload")
st.caption("Import a bank CSV export. Duplicates are skipped; the new rows are categorized.")

POLL_SECONDS = 1.0


def upload_with_progress(file_name: str, content: bytes) -> dict[str, Any]:
    """Upload in a background thread and show the LLM step's progress while it runs.

    The request is synchronous (CONTRACT §8.2): the API answers when the import is done, so
    the progress comes from polling the progress endpoint (§8.7a). Raises what the upload raises.
    """
    outcome: dict[str, Any] = {}

    def work() -> None:
        try:
            outcome["result"] = api.upload_import(file_name, content)
        except Exception as exc:  # re-raised in the script thread below
            outcome["error"] = exc

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    bar = st.progress(0.0, text="Parsing the file and applying the rules...")
    while thread.is_alive():
        time.sleep(POLL_SECONDS)
        try:
            progress = api.llm_progress()
        except (ApiError, ApiUnreachableError):
            continue  # the upload itself reports a real failure
        if progress["running"] and progress["total"]:
            done, total = progress["processed"], progress["total"]
            bar.progress(
                done / total, text=f"Categorizing with the LLM: {done} of {total} transactions"
            )
    bar.empty()
    if "error" in outcome:
        raise outcome["error"]
    result: dict[str, Any] = outcome["result"]
    return result


uploaded = st.file_uploader("Bank export (CSV)", type=["csv"])
if uploaded is not None and st.button("Import", type="primary"):
    try:
        result = upload_with_progress(uploaded.name, uploaded.getvalue())
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
