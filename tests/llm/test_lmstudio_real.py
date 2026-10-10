from datetime import date
from decimal import Decimal

import pytest

from kontor.adapters.llm.lmstudio import LMStudioClient
from kontor.config import Settings
from kontor.domain.transaction import Transaction

pytestmark = pytest.mark.llm

CATEGORIES = ["food.groceries", "transport.public", "housing.rent", "leisure.restaurants"]


@pytest.fixture
def client() -> LMStudioClient:
    s = Settings()
    return LMStudioClient(
        s.categorizer_llm_base_url,
        s.categorizer_llm_model,
        s.categorizer_llm_timeout_seconds,
        s.categorizer_llm_api_key,
    )


def test_server_is_reachable(client: LMStudioClient) -> None:
    assert client.is_healthy()


def test_clear_case_is_categorized_with_probability(client: LMStudioClient) -> None:
    tx = Transaction(
        booking_date=date(2026, 1, 5),
        amount=Decimal("-54.20"),
        currency="EUR",
        counterparty="REWE SAGT DANKE",
        purpose="Kartenzahlung Supermarkt",
    )
    suggestion = client.classify(tx, CATEGORIES)
    assert suggestion.category_slug == "food.groceries"
    assert 0.0 < suggestion.confidence <= 1.0
