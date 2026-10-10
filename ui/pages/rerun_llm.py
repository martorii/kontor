import streamlit as st

from api_client import ApiClient, ApiError, ApiTimeoutError, ApiUnreachableError
from progress import run_with_llm_progress

api = ApiClient.from_env()

st.title("Re-run LLM")
st.caption(
    "Ask the LLM again for every uncategorized transaction, for example after LM Studio was "
    "offline. Results above the confidence threshold are applied; the rest stay as suggestions. "
    "Manual categorizations are never touched."
)

dry_run = st.checkbox("Dry run (call the LLM but write nothing)")

if st.button("Run LLM on uncategorized transactions", type="primary"):
    try:
        result = run_with_llm_progress(
            api, lambda: api.run_llm(dry_run), "Starting the LLM step..."
        )
    except ApiError as exc:
        st.error(f"The LLM run failed: {exc.detail}")
    except ApiTimeoutError as exc:
        st.warning(
            f"{exc} The run may still be going on the API. Check **Import history** before "
            "starting it again."
        )
    except ApiUnreachableError as exc:
        st.error(str(exc))
    else:
        if result["skipped"]:
            st.warning("LM Studio is not reachable, so nothing was run.")
        else:
            if result["interrupted"]:
                st.warning("The run was interrupted. What was done so far is kept.")
            elif result["dry_run"]:
                st.info("Dry run finished. Nothing was written.")
            else:
                st.success("LLM run finished.")
            columns = st.columns(4)
            columns[0].metric("Evaluated", result["evaluated"])
            columns[1].metric("Applied", result["applied"])
            columns[2].metric("Suggested", result["suggested"])
            columns[3].metric("Failed", result["failed"])
