from collections.abc import Callable

from fastapi.testclient import TestClient
from helpers import dkb_file, row, upload
from sqlalchemy import Engine, text

from kontor.adapters.llm.fake import FakeLLMClient
from kontor.domain.llm import LLMSuggestion

RULES = """\
categories:
  - {slug: food, name: Food, kind: expense}
  - {slug: food.groceries, name: Groceries, parent: food}
  - {slug: shopping, name: Shopping, kind: expense}
  - {slug: shopping.home, name: Home, parent: shopping}
rules:
  - {id: rewe, category: food.groceries, field: counterparty, match: REWE}
"""

MakeClient = Callable[[str | None], TestClient]


def query(engine: Engine, sql: str) -> list[tuple[object, ...]]:
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text(sql))]


def state(engine: Engine) -> list[tuple[object, ...]]:
    return query(
        engine,
        "SELECT counterparty_raw, category_slug, category_source FROM transactions ORDER BY id",
    )


def counts(engine: Engine) -> tuple[object, ...]:
    return query(
        engine, "SELECT rule_matched_count, llm_matched_count, uncategorized_count FROM imports"
    )[0]


def ids(engine: Engine) -> dict[str, int]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT counterparty_raw, id FROM transactions"))
        return {name: tx_id for name, tx_id in rows}


def put(client: TestClient, transaction_id: int, category: str):  # type: ignore[no-untyped-def]
    return client.put(f"/transactions/{transaction_id}/category", json={"category": category})


def test_manual_override_is_recorded_with_source_manual(
    make_client: MakeClient, engine: Engine
) -> None:
    client = make_client(RULES)
    upload(client, dkb_file([row("10.03.26", "Shop", "-12,00")]))
    tx_id = ids(engine)["Shop"]

    response = put(client, tx_id, "shopping.home")

    assert response.status_code == 200
    assert response.json() == {
        "transaction_id": tx_id,
        "category": "shopping.home",
        "source": "manual",
    }
    assert state(engine) == [("Shop", "shopping.home", "manual")]
    assert query(engine, "SELECT source, applied, category_slug FROM categorization_events") == [
        ("manual", True, "shopping.home")
    ]
    assert counts(engine) == (0, 0, 0)  # no longer uncategorized


def test_override_replaces_a_rule_category_and_moves_the_counts(
    make_client: MakeClient, engine: Engine
) -> None:
    client = make_client(RULES)
    upload(client, dkb_file([row("10.03.26", "REWE Markt", "-12,00")]))
    assert counts(engine) == (1, 0, 0)

    put(client, ids(engine)["REWE Markt"], "shopping.home")

    assert state(engine) == [("REWE Markt", "shopping.home", "manual")]
    assert counts(engine) == (0, 0, 0)


def test_override_survives_rerun_and_llm_run(
    make_client: MakeClient, engine: Engine, fake_llm: FakeLLMClient
) -> None:
    client = make_client(RULES)
    upload(
        client,
        dkb_file([row("10.03.26", "REWE Markt", "-12,00"), row("11.03.26", "Shop", "-5,00")]),
    )
    tx = ids(engine)
    put(client, tx["REWE Markt"], "shopping.home")  # the rule would say food.groceries
    put(client, tx["Shop"], "food.groceries")
    fake_llm.healthy = True
    fake_llm.default = LLMSuggestion("shopping.home", 0.99)

    client.post("/categorization/rerun")
    llm = client.post("/categorization/llm").json()

    assert llm["evaluated"] == 0
    assert state(engine) == [
        ("REWE Markt", "shopping.home", "manual"),
        ("Shop", "food.groceries", "manual"),
    ]
    assert fake_llm.calls == []


def test_suggestions_are_listed_with_their_confidence(
    make_client: MakeClient, engine: Engine, fake_llm: FakeLLMClient
) -> None:
    client = make_client(RULES)
    upload(client, dkb_file([row("10.03.26", "Shop", "-12,00")]))
    fake_llm.healthy = True
    fake_llm.default = LLMSuggestion("food.groceries", 0.4)
    client.post("/categorization/llm")
    fake_llm.default = LLMSuggestion("shopping.home", 0.6)
    client.post("/categorization/llm")

    body = client.get("/transactions/uncategorized").json()

    assert body["total"] == 1
    item = body["items"][0]
    assert (item["counterparty"], item["amount"], item["currency"]) == ("Shop", "-12.00", "EUR")
    assert [(s["category"], s["confidence"], s["model"]) for s in item["suggestions"]] == [
        ("shopping.home", 0.6, "fake"),  # newest first
        ("food.groceries", 0.4, "fake"),
    ]


def test_list_only_has_uncategorized_transactions_and_paginates(
    make_client: MakeClient, engine: Engine
) -> None:
    client = make_client(RULES)
    upload(
        client,
        dkb_file(
            [
                row("10.03.26", "REWE Markt", "-1,00"),
                row("11.03.26", "Shop A", "-2,00"),
                row("12.03.26", "Shop B", "-3,00"),
                row("13.03.26", "Shop C", "-4,00"),
            ]
        ),
    )

    page = client.get("/transactions/uncategorized", params={"limit": 2, "offset": 1}).json()

    assert page["total"] == 3  # REWE was categorized by the rule
    assert (page["limit"], page["offset"]) == (2, 1)
    assert [i["counterparty"] for i in page["items"]] == ["Shop B", "Shop A"]  # newest first


def test_invalid_requests(make_client: MakeClient, engine: Engine) -> None:
    client = make_client(RULES)
    upload(client, dkb_file([row("10.03.26", "Shop", "-12,00")]))
    tx_id = ids(engine)["Shop"]

    assert put(client, 9999, "shopping.home").status_code == 404
    assert put(client, tx_id, "shopping").status_code == 422  # top-level
    assert put(client, tx_id, "nope.nothing").status_code == 422
    assert state(engine) == [("Shop", None, None)]
