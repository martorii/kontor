from collections.abc import Callable

from fastapi.testclient import TestClient
from helpers import dkb_file, row, upload
from test_reports import OTHER_IBAN, RULES, seed

MakeClient = Callable[[str | None], TestClient]


def names(client: TestClient, **params: str | int) -> list[str]:
    response = client.get("/transactions", params=params)
    assert response.status_code == 200
    return [item["counterparty"] for item in response.json()["items"]]


def test_explorer_without_filters_is_paginated_newest_first(make_client: MakeClient) -> None:
    client = make_client(RULES)
    seed(client)

    page = client.get("/transactions", params={"limit": 3}).json()

    assert page["total"] == 14
    assert [i["booking_date"] for i in page["items"]] == ["2026-04-25", "2026-04-14", "2026-03-29"]
    assert page["items"][0]["category"] == "salary.main"
    assert page["items"][0]["category_source"] == "rule"
    second = client.get("/transactions", params={"limit": 3, "offset": 3}).json()
    assert second["items"][0]["booking_date"] == "2026-03-28"


def test_date_range_filter_is_inclusive(make_client: MakeClient) -> None:
    client = make_client(RULES)
    seed(client)

    found = names(client, date_from="2026-03-25", date_to="2026-03-27")

    assert found == ["BROKER AG", "OWN ACCOUNT", "ACME Corp"]


def test_category_filter_includes_subcategories_of_a_top_level_category(
    make_client: MakeClient,
) -> None:
    client = make_client(RULES)
    seed(client)

    assert len(names(client, category="food", date_from="2026-01-01")) == 5
    assert names(client, category="food.restaurants") == ["CAFE Central"]


def test_text_filter_matches_counterparty_or_purpose_and_escapes_wildcards(
    make_client: MakeClient,
) -> None:
    client = make_client(RULES)
    seed(client)

    assert names(client, q="cafe") == ["CAFE Central"]
    assert (
        len(names(client, q="kartenzahlung", limit=100)) == 10
    )  # the purpose of the outgoing bookings
    assert names(client, q="%") == []


def test_source_filter(make_client: MakeClient) -> None:
    client = make_client(RULES)
    seed(client)
    mystery = client.get("/transactions", params={"q": "mystery"}).json()["items"][0]
    assert mystery["category"] is None

    assert names(client, source="none") == ["Mystery Shop"]
    assert names(client, source="manual") == []

    client.put(
        f"/transactions/{mystery['transaction_id']}/category", json={"category": "food.groceries"}
    )

    assert names(client, source="none") == []
    assert names(client, source="manual") == ["Mystery Shop"]
    assert len(names(client, source="rule", limit=100)) == 13


def test_account_filter(make_client: MakeClient) -> None:
    client = make_client(RULES)
    seed(client)
    upload(client, dkb_file([row("10.03.26", "Other Shop", "-1,00")], iban=OTHER_IBAN), "o.csv")
    accounts = {a["iban"]: a["id"] for a in client.get("/accounts").json()}

    assert names(client, account_id=accounts[OTHER_IBAN]) == ["Other Shop"]


def test_filters_combine_and_invalid_source_is_rejected(make_client: MakeClient) -> None:
    client = make_client(RULES)
    seed(client)

    assert names(client, category="food", date_from="2026-04-01") == ["REWE Markt"]
    assert client.get("/transactions", params={"source": "bogus"}).status_code == 422


def test_categories_lists_only_the_assignable_subcategories(make_client: MakeClient) -> None:
    client = make_client(RULES)

    categories = client.get("/categories").json()

    slugs = [c["slug"] for c in categories]
    assert "food" not in slugs
    assert {"food.groceries", "food.restaurants", "salary.main"} <= set(slugs)
    assert {"slug": "housing.rent", "name": "Rent", "parent_slug": "housing"} in categories
