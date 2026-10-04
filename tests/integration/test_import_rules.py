from collections.abc import Callable

from fastapi.testclient import TestClient
from helpers import dkb_file, row, upload
from sqlalchemy import Engine, text

RULES = """\
categories:
  - {slug: food, name: Food, kind: expense}
  - {slug: food.groceries, name: Groceries, parent: food}
  - {slug: shopping, name: Shopping, kind: expense}
  - {slug: shopping.home, name: Home, parent: shopping}
rules:
  - {id: rewe, category: food.groceries, field: counterparty, match: REWE}
  - {id: rewe-too, category: shopping.home, field: counterparty, match: REWE}
  - {id: big-spend, category: shopping.home, field: counterparty, match: Other,
     when: {amount_max: -100}}
"""


def query(engine: Engine, sql: str) -> list[tuple[object, ...]]:
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text(sql))]


def test_rules_categorize_during_import_with_provenance(
    make_client: Callable[[str | None], TestClient], engine: Engine
) -> None:
    client = make_client(RULES)
    content = dkb_file(
        [
            row("10.03.26", "REWE Markt", "-12,00"),
            row("11.03.26", "Unknown Shop", "-5,00"),
            row("12.03.26", "Other Shop", "-250,00"),
            row("13.03.26", "Other Kiosk", "-3,00"),
        ]
    )

    response = upload(client, content)

    assert response.json()["new_count"] == 4
    assert response.json()["rule_matched_count"] == 2
    assert response.json()["uncategorized_count"] == 2

    transactions = query(
        engine,
        "SELECT counterparty_raw, category_slug, category_source FROM transactions ORDER BY id",
    )
    assert transactions == [
        ("REWE Markt", "food.groceries", "rule"),  # first matching rule wins
        ("Unknown Shop", None, None),  # unmatched stays uncategorized
        ("Other Shop", "shopping.home", "rule"),  # condition satisfied
        ("Other Kiosk", None, None),  # pattern matches but the amount condition fails
    ]

    events = query(
        engine,
        "SELECT t.counterparty_raw, e.category_slug, e.source, e.applied, e.rule_id, "
        "e.rules_hash, e.model_name, e.confidence, e.created_at IS NOT NULL "
        "FROM categorization_events e JOIN transactions t ON t.id = e.transaction_id "
        "ORDER BY e.id",
    )
    assert len(events) == 2  # no event for the unmatched transaction
    rules_hash = events[0][5]
    assert isinstance(rules_hash, str) and len(rules_hash) == 64
    assert events == [
        ("REWE Markt", "food.groceries", "rule", True, "rewe", rules_hash, None, None, True),
        ("Other Shop", "shopping.home", "rule", True, "big-spend", rules_hash, None, None, True),
    ]


def test_reimporting_overlapping_rows_creates_no_extra_events(
    make_client: Callable[[str | None], TestClient], engine: Engine
) -> None:
    client = make_client(RULES)
    first = dkb_file([row("10.03.26", "REWE Markt", "-12,00")])
    second = dkb_file([row("10.03.26", "REWE Markt", "-12,00"), row("11.03.26", "Shop", "-1,00")])
    upload(client, first)

    response = upload(client, second)

    assert response.json()["new_count"] == 1
    assert response.json()["rule_matched_count"] == 0
    assert query(engine, "SELECT count(*) FROM categorization_events") == [(1,)]
