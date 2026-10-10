"""Run a blocking API call in a thread while showing the LLM step's progress."""

import threading
import time
from collections.abc import Callable
from typing import Any  # Any: JSON bodies are untyped by nature

import streamlit as st

from api_client import ApiClient, ApiError, ApiUnreachableError

POLL_SECONDS = 1.0


def run_with_llm_progress(
    api: ApiClient, call: Callable[[], dict[str, Any]], start_text: str
) -> dict[str, Any]:
    """Run `call` in a background thread and show the progress endpoint (CONTRACT §8.7a).

    The API answers only when the work is done (CONTRACT §8.2), so the progress comes from
    polling. Raises what `call` raises.
    """
    outcome: dict[str, Any] = {}

    def work() -> None:
        try:
            outcome["result"] = call()
        except Exception as exc:  # re-raised in the script thread below
            outcome["error"] = exc

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    bar = st.progress(0.0, text=start_text)
    while thread.is_alive():
        time.sleep(POLL_SECONDS)
        try:
            progress = api.llm_progress()
        except (ApiError, ApiUnreachableError):
            continue  # the call itself reports a real failure
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
