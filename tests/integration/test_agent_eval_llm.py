"""Three golden questions end to end with the real LM Studio (AGENT_LLM_* settings)."""

from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from sqlalchemy import Engine, text

from kontor.adapters.db.query_executor import PostgresQueryExecutor
from kontor.adapters.db.schema_introspector import PostgresSchemaIntrospector
from kontor.adapters.llm.lmstudio_agent import LMStudioAgentLLM
from kontor.agent_eval_cli import DEFAULT_GOLDEN, load_golden
from kontor.agent_eval_seed import seed
from kontor.application.agent import AgentService
from kontor.application.agent_context import load_notes
from kontor.application.agent_conversations import ConversationStore
from kontor.application.agent_evaluation import compute_metrics, evaluate_agent
from kontor.config import Settings

pytestmark = pytest.mark.llm


@pytest.fixture
def seeded(engine: Engine) -> Iterator[None]:
    seed(engine, date.today())
    yield
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE categorization_events, transactions, imports, accounts, categories "
                "RESTART IDENTITY CASCADE"
            )
        )


def test_three_golden_questions_run_end_to_end(engine: Engine, seeded: None) -> None:
    settings = Settings()
    if not settings.agent_llm_base_url or not settings.agent_llm_model:
        pytest.skip("AGENT_LLM_BASE_URL and AGENT_LLM_MODEL are not set")
    executor = PostgresQueryExecutor(engine, timeout_seconds=10, max_rows=500)
    service = AgentService(
        LMStudioAgentLLM(
            settings.agent_llm_base_url,
            settings.agent_llm_model,
            settings.agent_llm_timeout_seconds,
            settings.agent_llm_api_key,
        ),
        executor,
        PostgresSchemaIntrospector(engine).introspect(),
        load_notes(),
        ConversationStore(10, timedelta(hours=1)),
        max_retries=settings.agent_max_retries,
        summary_rows=settings.agent_summary_rows,
    )

    results = evaluate_agent(service, executor, load_golden(DEFAULT_GOLDEN)[:3])

    metrics = compute_metrics(results)
    assert metrics.questions == 3
    assert all(result.latency_seconds > 0 for result in results)
