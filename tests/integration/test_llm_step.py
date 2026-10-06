from collections.abc import Callable

from fastapi.testclient import TestClient
from helpers import dkb_file, row, upload
from sqlalchemy import Engine, text
from structlog.testing import capture_logs

from kontor.adapters.llm.fake import FakeLLMClient
from kontor.domain.llm import LLMSuggestion

RULES = """\
categories:
  - {slug: food, name: Food, kind: expense}
  - {slug: food.groceries, name: Groceries, parent: food}
  - {slug: shopping, name: Shopping, kind: expense}
  - {slug: shopping.home, name: Home, parent: shopping}
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
    return query(engine, "SELECT llm_matched_count, uncategorized_count FROM imports")[0]


def test_below_threshold_is_stored_as_a_suggestion(
    make_client: MakeClient, engine: Engine, fake_llm: FakeLLMClient
) -> None:
    fake_llm.healthy = True
    fake_llm.answers = {
        "Sure Shop": LLMSuggestion("food.groceries", 0.95),
        "Unsure Shop": LLMSuggestion("shopping.home", 0.5),
    }
    client = make_client(RULES)

    response = upload(
        client,
        dkb_file([row("10.03.26", "Sure Shop", "-12,00"), row("11.03.26", "Unsure Shop", "-5,00")]),
    )

    assert response.json()["llm_matched_count"] == 1
    assert response.json()["uncategorized_count"] == 1
    assert state(engine) == [
        ("Sure Shop", "food.groceries", "llm"),
        ("Unsure Shop", None, None),
    ]
    assert counts(engine) == (1, 1)
    events = query(
        engine,
        "SELECT t.counterparty_raw, e.category_slug, e.source, e.applied, e.model_name, "
        "e.confidence FROM categorization_events e JOIN transactions t "
        "ON t.id = e.transaction_id ORDER BY e.id",
    )
    assert [(e[0], e[1], e[2], e[3], e[4], float(e[5])) for e in events] == [  # type: ignore[arg-type]
        ("Sure Shop", "food.groceries", "llm", True, "fake", 0.95),
        ("Unsure Shop", "shopping.home", "llm", False, "fake", 0.5),
    ]


def test_unreachable_llm_does_not_fail_the_import(
    make_client: MakeClient, engine: Engine, fake_llm: FakeLLMClient
) -> None:
    client = make_client(RULES)  # the fake LLM is down by default

    with capture_logs() as logs:
        response = upload(client, dkb_file([row("10.03.26", "Shop", "-12,00")]))

    assert response.status_code == 201
    assert response.json()["uncategorized_count"] == 1
    assert fake_llm.calls == []
    warnings = [entry for entry in logs if entry["log_level"] == "warning"]
    assert [entry["event"] for entry in warnings] == ["llm_step_skipped"]
    assert state(engine) == [("Shop", None, None)]


def test_interruption_keeps_imported_rows_and_committed_batches(
    make_client: MakeClient, engine: Engine, fake_llm: FakeLLMClient
) -> None:
    fake_llm.healthy = True
    fake_llm.default = LLMSuggestion("shopping.home", 0.9)
    fake_llm.crash_on_call = 15  # second batch of 10
    client = make_client(RULES)

    response = upload(
        client,
        dkb_file([row("10.03.26", f"Shop {n}", f"-{n + 1},00") for n in range(25)]),
    )

    assert response.status_code == 201
    assert response.json()["new_count"] == 25
    assert response.json()["llm_matched_count"] == 10
    assert response.json()["uncategorized_count"] == 15
    assert len(state(engine)) == 25
    assert sum(1 for r in state(engine) if r[2] == "llm") == 10
    assert counts(engine) == (10, 15)


def test_on_demand_run_dry_run_then_real_run(
    make_client: MakeClient, engine: Engine, fake_llm: FakeLLMClient
) -> None:
    client = make_client(RULES)
    upload(
        client,
        dkb_file([row("10.03.26", "Shop A", "-1,00"), row("11.03.26", "Shop B", "-2,00")]),
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE transactions SET category_slug = 'shopping.home', "
                "category_source = 'manual' WHERE counterparty_raw = 'Shop B'"
            )
        )
    fake_llm.healthy = True
    fake_llm.default = LLMSuggestion("food.groceries", 0.4)

    # First run: below the threshold, so only a suggestion is stored.
    low = client.post("/categorization/llm").json()
    assert (low["evaluated"], low["applied"], low["suggested"]) == (1, 0, 1)

    # LM Studio gets better answers; the transaction with a suggestion is asked again.
    fake_llm.default = LLMSuggestion("food.groceries", 0.9)
    dry = client.post("/categorization/llm", params={"dry_run": True}).json()
    assert dry["dry_run"] is True
    assert (dry["evaluated"], dry["applied"]) == (1, 1)
    assert state(engine) == [("Shop A", None, None), ("Shop B", "shopping.home", "manual")]

    real = client.post("/categorization/llm").json()
    assert real["applied"] == 1
    assert state(engine) == [
        ("Shop A", "food.groceries", "llm"),
        ("Shop B", "shopping.home", "manual"),  # manual is never overwritten
    ]
    # Shop B was made manual behind the import's back, so it still counts as uncategorized.
    assert counts(engine) == (1, 1)


def test_on_demand_run_is_skipped_when_llm_is_down(
    make_client: MakeClient, fake_llm: FakeLLMClient
) -> None:
    client = make_client(RULES)
    upload(client, dkb_file([row("10.03.26", "Shop A", "-1,00")]))

    body = client.post("/categorization/llm").json()

    assert body["skipped"] is True
    assert body["evaluated"] == 0


def test_progress_is_idle_before_a_run_and_complete_after_it(
    make_client: MakeClient, fake_llm: FakeLLMClient
) -> None:
    fake_llm.healthy = True
    fake_llm.default = LLMSuggestion("food.groceries", 0.95)
    client = make_client(RULES)

    assert client.get("/categorization/llm/progress").json() == {
        "running": False,
        "processed": 0,
        "total": 0,
        "import_id": None,
    }

    upload(client, dkb_file([row("10.03.26", "A", "-1,00"), row("11.03.26", "B", "-2,00")]))

    progress = client.get("/categorization/llm/progress").json()
    assert progress["running"] is False
    assert (progress["processed"], progress["total"]) == (2, 2)
    assert progress["import_id"] is not None
