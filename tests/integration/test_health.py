from fastapi.testclient import TestClient

from kontor.api.app import create_app
from kontor.config import Settings


def test_health_returns_200() -> None:
    settings = Settings(
        categorizer_llm_base_url="http://llm.test/v1",
        categorizer_llm_model="test-model",
        agent_llm_base_url="http://llm.test/v1",
        agent_llm_model="test-model",
    )
    client = TestClient(create_app(settings))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
