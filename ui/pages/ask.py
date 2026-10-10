from contextlib import suppress
from typing import Any  # Any: JSON bodies are untyped by nature

import streamlit as st

from agent_view import chart_data
from api_client import ApiClient, ApiError, ApiTimeoutError, ApiUnreachableError

api = ApiClient.from_env()

CONVERSATION = "ask_conversation_id"
MESSAGES = "ask_messages"

st.session_state.setdefault(CONVERSATION, None)
st.session_state.setdefault(MESSAGES, [])


def new_conversation() -> None:
    conversation_id = st.session_state[CONVERSATION]
    if conversation_id is not None:
        # Unknown, expired or unreachable: there is nothing left to forget.
        with suppress(ApiError, ApiUnreachableError):
            api.forget_conversation(conversation_id)
    st.session_state[CONVERSATION] = None
    st.session_state[MESSAGES] = []


def render_answer(response: dict[str, Any]) -> None:
    if response["status"] == "gave_up":
        st.warning(response["answer"])
        if response["last_error"]:
            st.caption(f"Last error: {response['last_error']}")
        if response["sql"]:
            with st.expander("Last SQL tried"):
                st.code(response["sql"], language="sql")
        return

    st.markdown(response["answer"])
    if response["columns"]:
        st.dataframe(
            [dict(zip(response["columns"], row, strict=True)) for row in response["rows"]],
            hide_index=True,
        )
        if response["truncated"]:
            st.caption(f"Showing the first {len(response['rows'])} rows; the query returned more.")
    data = chart_data(response)
    if data is not None:
        x, y = response["chart"]["x"], response["chart"]["y"]
        if response["chart"]["type"] == "line":
            st.line_chart(data, x=x, y=y)
        else:
            st.bar_chart(data, x=x, y=y)
    with st.expander("SQL"):
        st.code(response["sql"], language="sql")
    st.caption(f"Attempts: {response['attempts']}")


st.title("Ask")
st.caption(
    "Ask questions about your transactions in plain language. The agent writes a read-only SQL "
    "query, runs it, and answers from the result. Follow-up questions keep the context."
)

with st.sidebar:
    st.button("New conversation", on_click=new_conversation, icon="🧹")

for message in st.session_state[MESSAGES]:
    with st.chat_message(message["role"]):
        if message["role"] == "user":
            st.markdown(message["text"])
        else:
            if message.get("restarted"):
                st.caption("The previous conversation had expired, so a new one was started.")
            render_answer(message["response"])

question = st.chat_input("How much did I spend on groceries last month?")
if question:
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        sent_id = st.session_state[CONVERSATION]
        try:
            with st.spinner("Writing and running a query..."):
                response = api.ask(question, sent_id)
        except ApiError as exc:
            if exc.status_code == 503:
                st.error(f"LM Studio is not reachable: {exc.detail}")
            else:
                st.error(f"The question failed: {exc.detail}")
        except ApiTimeoutError as exc:
            st.warning(f"{exc} The agent may still be working; try again in a moment.")
        except ApiUnreachableError as exc:
            st.error(str(exc))
        else:
            restarted = sent_id is not None and response["conversation_id"] != sent_id
            if restarted:
                st.caption("The previous conversation had expired, so a new one was started.")
            render_answer(response)
            st.session_state[CONVERSATION] = response["conversation_id"]
            st.session_state[MESSAGES] += [
                {"role": "user", "text": question},
                {"role": "assistant", "response": response, "restarted": restarted},
            ]
