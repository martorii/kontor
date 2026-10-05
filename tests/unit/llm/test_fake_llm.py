from datetime import date
from decimal import Decimal

import pytest

from kontor.adapters.llm.fake import FakeLLMClient
from kontor.domain.errors import LLMInvalidOutputError, LLMTimeoutError, LLMUnavailableError
from kontor.domain.llm import LLMSuggestion
from kontor.domain.transaction import Transaction

CATEGORIES = ["food.groceries", "transport"]


def tx(counterparty: str = "SHOP") -> Transaction:
    return Transaction(
        booking_date=date(2026, 1, 5),
        amount=Decimal("-12.50"),
        currency="EUR",
        counterparty=counterparty,
        purpose="",
    )


def test_valid_output() -> None:
    suggestion = LLMSuggestion("food.groceries", 0.93)
    client = FakeLLMClient(default=suggestion)
    assert client.classify(tx(), CATEGORIES) == suggestion


def test_category_outside_the_list_is_rejected() -> None:
    client = FakeLLMClient(default=LLMSuggestion("invented", 0.99))
    with pytest.raises(LLMInvalidOutputError):
        client.classify(tx(), CATEGORIES)


def test_timeout() -> None:
    client = FakeLLMClient(default=LLMSuggestion("transport", 0.9), timeout=True)
    with pytest.raises(LLMTimeoutError):
        client.classify(tx(), CATEGORIES)


def test_unreachable_server() -> None:
    client = FakeLLMClient(healthy=False)
    assert not client.is_healthy()
    with pytest.raises(LLMUnavailableError):
        client.classify(tx(), CATEGORIES)


def test_confidence_must_be_a_probability() -> None:
    with pytest.raises(ValueError):
        LLMSuggestion("transport", 1.5)
