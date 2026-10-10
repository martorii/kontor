import json
from datetime import date
from decimal import Decimal

import httpx2 as httpx
import pytest
from openai import OpenAI

from kontor.adapters.llm.lmstudio_agent import (
    PROMPT_TEXT,
    SQL_SYSTEM_PROMPT,
    LMStudioAgentLLM,
    parse_sql_answer,
    parse_summary_answer,
    render_sql_request,
    render_summary_request,
)
from kontor.domain.agent import ChartSpec, FailedAttempt, Summary, Turn
from kontor.domain.errors import LLMInvalidOutputError, LLMTimeoutError, LLMUnavailableError


def completion(content: str) -> dict[str, object]:
    return {
        "id": "x",
        "object": "chat.completion",
        "created": 0,
        "model": "m",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content},
            }
        ],
    }


def agent_with(handler: httpx.MockTransport) -> LMStudioAgentLLM:
    sdk = OpenAI(
        base_url="http://lm.test/v1",
        api_key="k",
        max_retries=0,
        http_client=httpx.Client(transport=handler),
    )
    return LMStudioAgentLLM("http://lm.test/v1", "m", 1.0, client=sdk)


def test_generate_sql_sends_the_context_and_parses_the_answer() -> None:
    sent: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=completion('{"sql": " SELECT 1 "}'))

    sql = agent_with(httpx.MockTransport(handler)).generate_sql("q?", [], "CONTEXT", [])

    assert sql == "SELECT 1"
    messages = sent[0]["messages"]
    assert isinstance(messages, list)
    assert messages[0]["content"] == f"{SQL_SYSTEM_PROMPT}\nCONTEXT"
    assert "Question: q?" in messages[1]["content"]
    assert sent[0]["temperature"] == 0


def test_summarize_parses_answer_and_chart() -> None:
    answer = {"answer": "You spent 10.", "chart": {"type": "bar", "x": "m", "y": "spent"}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=completion(json.dumps(answer)))

    summary = agent_with(httpx.MockTransport(handler)).summarize(
        "q?", "SELECT 1", ["m", "spent"], [["Jan", Decimal("10.00")]], False
    )

    assert summary == Summary("You spent 10.", ChartSpec("bar", "m", "spent"))


def test_timeout_is_mapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(LLMTimeoutError):
        agent_with(httpx.MockTransport(handler)).generate_sql("q", [], "", [])


def test_connection_error_is_mapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    with pytest.raises(LLMUnavailableError):
        agent_with(httpx.MockTransport(handler)).generate_sql("q", [], "", [])


def test_empty_content_is_invalid() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=completion(""))

    with pytest.raises(LLMInvalidOutputError):
        agent_with(httpx.MockTransport(handler)).generate_sql("q", [], "", [])


@pytest.mark.parametrize("content", ["not json", '{"query": "SELECT 1"}', '{"sql": "  "}', "[]"])
def test_parse_sql_answer_rejects_unusable_output(content: str) -> None:
    with pytest.raises(LLMInvalidOutputError):
        parse_sql_answer(content)


def test_parse_summary_answer_with_no_chart() -> None:
    content = '{"answer": " Nothing. ", "chart": {"type": "none", "x": "a", "y": "b"}}'

    assert parse_summary_answer(content) == Summary("Nothing.", ChartSpec("none"))


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        '{"answer": "x"}',
        '{"answer": "", "chart": {"type": "none", "x": "", "y": ""}}',
        '{"answer": "x", "chart": {"type": "pie", "x": "", "y": ""}}',
        '{"answer": "x", "chart": {"type": "bar"}}',
    ],
)
def test_parse_summary_answer_rejects_unusable_output(content: str) -> None:
    with pytest.raises(LLMInvalidOutputError):
        parse_summary_answer(content)


def test_sql_request_holds_history_and_failed_attempts() -> None:
    text = render_sql_request(
        "And February?",
        [Turn("January?", "SELECT 1", "120.50")],
        [FailedAttempt("SELECT nope", 'column "nope" does not exist'), FailedAttempt(None, "bad")],
        date(2026, 3, 1),
    )

    assert "Today is 2026-03-01." in text
    assert "Question: January?\nSQL: SELECT 1\nAnswer: 120.50" in text
    assert text.index("January?") < text.index("Question: And February?")
    assert 'SQL: SELECT nope\nError: column "nope" does not exist' in text
    assert "SQL: (no usable output)\nError: bad" in text


def test_sql_request_without_history_or_failures_is_just_the_question() -> None:
    text = render_sql_request("q?", [], [], date(2026, 3, 1))

    assert text == "Today is 2026-03-01.\n\nQuestion: q?"


def test_summary_request_renders_rows_and_truncation() -> None:
    text = render_summary_request(
        "q?", "SELECT 1", ["m", "spent"], [["Jan", Decimal("10.50")], ["Feb", None]], True
    )

    assert "m | spent\nJan | 10.50\nFeb | NULL" in text
    assert "(Only the first 2 rows are shown.)" in text


def test_prompt_text_covers_prompts_and_templates() -> None:
    assert SQL_SYSTEM_PROMPT in PROMPT_TEXT
    assert "Earlier in this conversation" in PROMPT_TEXT
    assert "Only the first" in PROMPT_TEXT
