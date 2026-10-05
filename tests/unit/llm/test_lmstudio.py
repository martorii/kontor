import json
import math
from datetime import date
from decimal import Decimal

import httpx2 as httpx
import pytest
from openai import OpenAI

from kontor.adapters.llm.lmstudio import LMStudioClient, parse_answer
from kontor.domain.errors import LLMInvalidOutputError, LLMTimeoutError, LLMUnavailableError
from kontor.domain.transaction import Transaction

CATEGORIES = ["food.groceries", "transport"]
TX = Transaction(
    booking_date=date(2026, 1, 5),
    amount=Decimal("-12.50"),
    currency="EUR",
    counterparty="SHOP",
    purpose="",
)


def completion(content: str, tokens: list[tuple[str, float]] | None) -> dict[str, object]:
    logprobs = (
        None
        if tokens is None
        else {"content": [{"token": t, "logprob": lp, "top_logprobs": []} for t, lp in tokens]}
    )
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
                "logprobs": logprobs,
            }
        ],
    }


def client_with(handler: httpx.MockTransport) -> LMStudioClient:
    sdk = OpenAI(
        base_url="http://lm.test/v1",
        api_key="k",
        max_retries=0,
        http_client=httpx.Client(transport=handler),
    )
    return LMStudioClient("http://lm.test/v1", "m", 1.0, client=sdk)


TOKENS = [('{"category": "', -0.0), ("food", -0.1), (".gro", -0.2), ("ceries", -0.0), ('"}', 0.0)]


def test_confidence_is_the_probability_of_the_category_tokens() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json=completion('{"category": "food.groceries"}', TOKENS))

    suggestion = client_with(httpx.MockTransport(handler)).classify(TX, CATEGORIES)

    assert suggestion.category_slug == "food.groceries"
    assert suggestion.confidence == pytest.approx(math.exp(-0.3))
    schema = seen["response_format"]["json_schema"]["schema"]  # type: ignore[index]
    assert schema["properties"]["category"]["enum"] == CATEGORIES
    assert seen["logprobs"] is True


def test_category_outside_the_list_is_rejected() -> None:
    with pytest.raises(LLMInvalidOutputError):
        parse_answer('{"category": "invented"}', [('{"category": "invented"}', -0.1)], CATEGORIES)


def test_missing_logprobs_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=completion('{"category": "transport"}', None))

    with pytest.raises(LLMInvalidOutputError):
        client_with(httpx.MockTransport(handler)).classify(TX, CATEGORIES)


def test_malformed_json_is_rejected() -> None:
    with pytest.raises(LLMInvalidOutputError):
        parse_answer("not json", [("not json", -0.1)], CATEGORIES)


def test_timeout_is_mapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(LLMTimeoutError):
        client_with(httpx.MockTransport(handler)).classify(TX, CATEGORIES)


def test_connection_error_is_mapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    client = client_with(httpx.MockTransport(handler))
    with pytest.raises(LLMUnavailableError):
        client.classify(TX, CATEGORIES)
    assert not client.is_healthy()


def test_health_check_ok() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"object": "list", "data": []})

    assert client_with(httpx.MockTransport(handler)).is_healthy()
