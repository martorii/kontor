from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient
from helpers import dkb_file, row, upload
from sqlalchemy import Engine, text

HEADER_YAML = """\
categories:
  - {slug: food, name: Food, kind: expense}
  - {slug: food.groceries, name: Groceries, parent: food}
  - {slug: shopping, name: Shopping, kind: expense}
  - {slug: shopping.home, name: Home, parent: shopping}
"""
REWE = "  - {id: rewe, category: food.groceries, field: counterparty, match: REWE}\n"
RULES_NONE = HEADER_YAML
RULES_REWE = HEADER_YAML + "rules:\n" + REWE


def query(engine: Engine, sql: str) -> list[tuple[object, ...]]:
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text(sql))]


def execute(engine: Engine, sql: str) -> None:
    with engine.begin() as conn:
        conn.execute(text(sql))


def state(engine: Engine) -> list[tuple[object, ...]]:
    return query(
        engine,
        "SELECT counterparty_raw, category_slug, category_source FROM transactions ORDER BY id",
    )


def event_count(engine: Engine) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text("SELECT count(*) FROM categorization_events")).scalar_one())


def setup_rewe_transaction(
    make_client: Callable[[str | None], TestClient], engine: Engine, source: str
) -> TestClient:
    """One REWE transaction imported with no rules, then marked as categorized by `source`."""
    client = make_client(RULES_NONE)
    upload(client, dkb_file([row("10.03.26", "REWE Markt", "-12,00")]))
    execute(
        engine,
        f"UPDATE transactions SET category_slug = 'shopping.home', category_source = '{source}'",
    )
    return client


def test_manual_categorization_is_untouched(
    make_client: Callable[[str | None], TestClient], engine: Engine, tmp_path: Path
) -> None:
    client = setup_rewe_transaction(make_client, engine, "manual")
    (tmp_path / "rules.yaml").write_text(RULES_REWE)

    response = client.post("/categorization/rerun")

    assert response.status_code == 200
    assert response.json()["evaluated"] == 0
    assert response.json()["changed"] == 0
    assert state(engine) == [("REWE Markt", "shopping.home", "manual")]
    assert event_count(engine) == 0


def test_rule_replaces_llm_result(
    make_client: Callable[[str | None], TestClient], engine: Engine, tmp_path: Path
) -> None:
    client = setup_rewe_transaction(make_client, engine, "llm")
    (tmp_path / "rules.yaml").write_text(RULES_REWE)

    response = client.post("/categorization/rerun")

    body = response.json()
    assert (body["evaluated"], body["changed"], body["unchanged"]) == (1, 1, 0)
    assert body["changes"] == [
        {
            "transaction_id": 1,
            "old_category": "shopping.home",
            "old_source": "llm",
            "new_category": "food.groceries",
            "rule_id": "rewe",
        }
    ]
    assert state(engine) == [("REWE Markt", "food.groceries", "rule")]
    events = query(
        engine,
        "SELECT category_slug, source, applied, rule_id, rules_hash FROM categorization_events",
    )
    assert events == [("food.groceries", "rule", True, "rewe", body["rules_hash"])]


def test_llm_result_is_kept_when_no_rule_matches(
    make_client: Callable[[str | None], TestClient], engine: Engine, tmp_path: Path
) -> None:
    client = setup_rewe_transaction(make_client, engine, "llm")
    (tmp_path / "rules.yaml").write_text(
        RULES_NONE
        + "rules:\n  - {id: x, category: food.groceries, field: counterparty, match: EDEKA}\n"
    )

    response = client.post("/categorization/rerun")

    assert (response.json()["evaluated"], response.json()["changed"]) == (1, 0)
    assert state(engine) == [("REWE Markt", "shopping.home", "llm")]
    assert event_count(engine) == 0


def test_dry_run_writes_nothing(
    make_client: Callable[[str | None], TestClient], engine: Engine, tmp_path: Path
) -> None:
    client = setup_rewe_transaction(make_client, engine, "llm")
    new_rules = RULES_REWE.replace(
        "  - {slug: shopping, name: Shopping, kind: expense}\n",
        "  - {slug: shopping, name: Shopping, kind: expense}\n"
        "  - {slug: pets, name: Pets, kind: expense}\n"
        "  - {slug: pets.vet, name: Vet, parent: pets}\n",
    )
    (tmp_path / "rules.yaml").write_text(new_rules)
    categories_before = query(engine, "SELECT slug FROM categories ORDER BY slug")

    response = client.post("/categorization/rerun", params={"dry_run": "true"})

    body = response.json()
    assert body["dry_run"] is True
    assert body["changed"] == 1  # reported, not applied
    assert state(engine) == [("REWE Markt", "shopping.home", "llm")]
    assert event_count(engine) == 0
    assert query(engine, "SELECT slug FROM categories ORDER BY slug") == categories_before
    # The preview did not activate the new rules: a following import still uses the old ones.
    upload(client, dkb_file([row("11.03.26", "REWE Markt", "-3,00")]))
    assert state(engine)[1] == ("REWE Markt", None, None)


def test_invalid_yaml_keeps_the_old_rules_active(
    make_client: Callable[[str | None], TestClient], engine: Engine, tmp_path: Path
) -> None:
    client = make_client(RULES_REWE)
    (tmp_path / "rules.yaml").write_text("categories: [broken\n")

    response = client.post("/categorization/rerun")

    assert response.status_code == 422
    assert response.json()["error"] == "RulesFileError"
    assert "invalid YAML" in response.json()["detail"]
    upload(client, dkb_file([row("10.03.26", "REWE Markt", "-12,00")]))
    assert state(engine) == [("REWE Markt", "food.groceries", "rule")]


def test_rule_result_is_reset_when_the_rule_is_removed(
    make_client: Callable[[str | None], TestClient], engine: Engine, tmp_path: Path
) -> None:
    client = make_client(RULES_REWE)
    upload(client, dkb_file([row("10.03.26", "REWE Markt", "-12,00")]))
    (tmp_path / "rules.yaml").write_text(RULES_NONE)

    response = client.post("/categorization/rerun")

    assert response.json()["changed"] == 1
    assert state(engine) == [("REWE Markt", None, None)]
    last = query(
        engine, "SELECT category_slug, source, rule_id FROM categorization_events ORDER BY id DESC"
    )[0]
    assert last == (None, "rule", None)


def test_rerun_syncs_new_categories_and_is_idempotent(
    make_client: Callable[[str | None], TestClient], engine: Engine, tmp_path: Path
) -> None:
    client = make_client(RULES_NONE)
    upload(client, dkb_file([row("10.03.26", "Vet Clinic", "-60,00")]))
    (tmp_path / "rules.yaml").write_text(
        RULES_NONE.replace(
            "  - {slug: shopping, name: Shopping, kind: expense}\n",
            "  - {slug: shopping, name: Shopping, kind: expense}\n"
            "  - {slug: pets, name: Pets, kind: expense}\n"
            "  - {slug: pets.vet, name: Vet, parent: pets}\n",
        )
        + "rules:\n  - {id: vet, category: pets.vet, field: counterparty, match: VET}\n"
    )

    first = client.post("/categorization/rerun").json()
    second = client.post("/categorization/rerun").json()

    assert first["changed"] == 1
    assert (second["evaluated"], second["changed"], second["unchanged"]) == (1, 0, 1)
    assert state(engine) == [("Vet Clinic", "pets.vet", "rule")]
    assert event_count(engine) == 1
