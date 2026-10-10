"""The agent API (CONTRACT §16) on real Postgres: real introspection and executor, fake LLM."""

import pytest
from fastapi.testclient import TestClient

from kontor.adapters.llm.fake_agent import FakeAgentLLM
from kontor.application.agent import GAVE_UP_ANSWER
from kontor.domain.agent import NO_CHART, ChartSpec, Summary
from kontor.domain.errors import LLMTimeoutError, LLMUnavailableError

VALUES_SQL = (
    "SELECT DATE '2026-01-15' AS day, -12.34::numeric(12,2) AS amount, "
    "0.5::double precision AS share, true AS flag, NULL AS nothing"
)


def test_answered_returns_sql_rows_and_chart(
    client: TestClient, fake_agent_llm: FakeAgentLLM
) -> None:
    fake_agent_llm.sql = [VALUES_SQL]
    fake_agent_llm.summaries = [Summary("You spent 12.34.", ChartSpec("bar", "day", "amount"))]

    response = client.post("/agent/ask", json={"question": "What did I spend?"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "answered"
    assert body["answer"] == "You spent 12.34."
    assert body["sql"] == VALUES_SQL
    assert body["columns"] == ["day", "amount", "share", "flag", "nothing"]
    assert body["rows"] == [["2026-01-15", "-12.34", 0.5, True, None]]
    assert body["truncated"] is False
    assert body["chart"] == {"type": "bar", "x": "day", "y": "amount"}
    assert body["attempts"] == 1
    assert body["last_error"] is None
    assert body["trace"] == [{"attempt": 1, "sql": VALUES_SQL, "error": None, "rows": 1}]
    assert body["conversation_id"]


def test_money_is_never_a_float(client: TestClient, fake_agent_llm: FakeAgentLLM) -> None:
    fake_agent_llm.sql = ["SELECT 0.1::numeric(12,2) + 0.2::numeric(12,2) AS total"]
    fake_agent_llm.summaries = [Summary("ok", NO_CHART)]

    response = client.post("/agent/ask", json={"question": "q"})

    assert '"0.30"' in response.text
    assert response.json()["rows"] == [["0.30"]]


def test_reads_the_real_views(client: TestClient, fake_agent_llm: FakeAgentLLM) -> None:
    fake_agent_llm.sql = ["SELECT COUNT(*) AS n FROM v_flows"]
    fake_agent_llm.summaries = [Summary("None yet.", NO_CHART)]

    body = client.post("/agent/ask", json={"question": "How many?"}).json()

    assert body["rows"] == [[0]]
    assert "view v_flows" in fake_agent_llm.sql_calls[0].context


def test_postgres_error_is_retried(client: TestClient, fake_agent_llm: FakeAgentLLM) -> None:
    fake_agent_llm.sql = ["SELECT nope FROM v_flows", "SELECT COUNT(*) AS n FROM v_flows"]
    fake_agent_llm.summaries = [Summary("ok", NO_CHART)]

    body = client.post("/agent/ask", json={"question": "q"}).json()

    assert body["status"] == "answered"
    assert body["attempts"] == 2
    assert "nope" in fake_agent_llm.sql_calls[1].failed_attempts[0].error
    failed, answered = body["trace"]
    assert (failed["attempt"], failed["sql"], failed["rows"]) == (
        1,
        "SELECT nope FROM v_flows",
        None,
    )
    assert "nope" in failed["error"]
    assert answered == {
        "attempt": 2,
        "sql": "SELECT COUNT(*) AS n FROM v_flows",
        "error": None,
        "rows": 1,
    }


def test_gave_up_carries_the_last_sql_and_error(
    client: TestClient, fake_agent_llm: FakeAgentLLM
) -> None:
    fake_agent_llm.sql = [
        "SELECT nope FROM v_flows",
        "DELETE FROM accounts",
        "SELECT * FROM alembic_version",
    ]

    body = client.post("/agent/ask", json={"question": "q"}).json()

    assert body["status"] == "gave_up"
    assert body["answer"] == GAVE_UP_ANSWER
    assert body["attempts"] == 3
    assert body["sql"] == "SELECT * FROM alembic_version"
    assert "alembic_version" in body["last_error"]
    assert body["columns"] == []
    assert body["rows"] == []
    assert body["chart"] == {"type": "none", "x": None, "y": None}
    assert [record["attempt"] for record in body["trace"]] == [1, 2, 3]
    assert body["trace"][-1]["sql"] == "SELECT * FROM alembic_version"


def test_follow_up_continues_the_conversation(
    client: TestClient, fake_agent_llm: FakeAgentLLM
) -> None:
    fake_agent_llm.sql = ["SELECT 1 AS n", "SELECT 2 AS n"]
    fake_agent_llm.summaries = [Summary("One.", NO_CHART), Summary("Two.", NO_CHART)]

    first = client.post("/agent/ask", json={"question": "First?"}).json()
    second = client.post(
        "/agent/ask", json={"question": "And then?", "conversation_id": first["conversation_id"]}
    ).json()

    assert second["conversation_id"] == first["conversation_id"]
    (turn,) = fake_agent_llm.sql_calls[1].history
    assert (turn.question, turn.sql, turn.answer) == ("First?", "SELECT 1 AS n", "One.")


def test_unknown_conversation_gets_a_new_id(
    client: TestClient, fake_agent_llm: FakeAgentLLM
) -> None:
    fake_agent_llm.sql = ["SELECT 1 AS n"]
    fake_agent_llm.summaries = [Summary("ok", NO_CHART)]

    body = client.post("/agent/ask", json={"question": "q", "conversation_id": "gone"}).json()

    assert body["conversation_id"] != "gone"
    assert fake_agent_llm.sql_calls[0].history == ()


@pytest.mark.parametrize("error", [LLMUnavailableError("down"), LLMTimeoutError("slow")])
def test_llm_failures_return_503(
    client: TestClient, fake_agent_llm: FakeAgentLLM, error: Exception
) -> None:
    fake_agent_llm.sql = [error]

    response = client.post("/agent/ask", json={"question": "q"})

    assert response.status_code == 503
    assert response.json()["error"] == type(error).__name__


@pytest.mark.parametrize(
    "payload",
    [
        {"question": ""},
        {"question": "   "},
        {"question": "x" * 2001},
        {},
        {"question": "q", "unexpected": 1},
    ],
)
def test_invalid_requests_return_422(client: TestClient, payload: dict[str, object]) -> None:
    assert client.post("/agent/ask", json=payload).status_code == 422


def test_question_is_stripped(client: TestClient, fake_agent_llm: FakeAgentLLM) -> None:
    fake_agent_llm.sql = ["SELECT 1 AS n"]
    fake_agent_llm.summaries = [Summary("ok", NO_CHART)]

    client.post("/agent/ask", json={"question": "  q?  "})

    assert fake_agent_llm.sql_calls[0].question == "q?"


def test_delete_conversation(client: TestClient, fake_agent_llm: FakeAgentLLM) -> None:
    fake_agent_llm.sql = ["SELECT 1 AS n", "SELECT 2 AS n"]
    fake_agent_llm.summaries = [Summary("ok", NO_CHART), Summary("ok", NO_CHART)]
    conversation_id = client.post("/agent/ask", json={"question": "q"}).json()["conversation_id"]

    assert client.delete(f"/agent/conversations/{conversation_id}").status_code == 204
    assert client.delete(f"/agent/conversations/{conversation_id}").status_code == 404

    body = client.post(
        "/agent/ask", json={"question": "again", "conversation_id": conversation_id}
    ).json()
    assert body["conversation_id"] != conversation_id
    assert fake_agent_llm.sql_calls[1].history == ()
