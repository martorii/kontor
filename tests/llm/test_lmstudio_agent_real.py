"""The agent adapter against the real LM Studio (AGENT_LLM_* in .env). No database needed."""

import pytest

from kontor.adapters.llm.lmstudio_agent import LMStudioAgentLLM
from kontor.application.agent_context import load_notes, render_schema
from kontor.application.sql_validator import validate_query
from kontor.config import Settings
from kontor.domain.schema import Column, ForeignKey, Relation, SchemaInfo

pytestmark = pytest.mark.llm

SCHEMA = SchemaInfo(
    relations=(
        Relation(
            "v_flows",
            "view",
            (
                Column("transaction_id", "bigint"),
                Column("account_id", "bigint"),
                Column("currency", "character varying(3)"),
                Column("booking_date", "date"),
                Column("year", "integer"),
                Column("month", "integer"),
                Column("counterparty_normalized", "text"),
                Column("amount", "numeric(12,2)"),
                Column("uncategorized", "boolean"),
                Column("top_slug", "text"),
                Column("top_name", "text"),
                Column("sub_slug", "text"),
                Column("sub_name", "text"),
                Column("flow", "text"),
            ),
        ),
        Relation("accounts", "table", (Column("id", "bigint"), Column("name", "text"))),
    ),
    foreign_keys=(ForeignKey("v_flows", "account_id", "accounts", "id"),),
)


@pytest.fixture
def agent() -> LMStudioAgentLLM:
    s = Settings()
    if not s.agent_llm_base_url or not s.agent_llm_model:
        pytest.skip("AGENT_LLM_BASE_URL and AGENT_LLM_MODEL are not set")
    return LMStudioAgentLLM(
        s.agent_llm_base_url, s.agent_llm_model, s.agent_llm_timeout_seconds, s.agent_llm_api_key
    )


def test_generates_a_valid_select(agent: LMStudioAgentLLM) -> None:
    context = f"{load_notes()}\n\n# Schema\n\n{render_schema(SCHEMA)}"

    sql = agent.generate_sql("How much did I spend on groceries last month?", [], context, [])

    assert sql.lstrip().upper().startswith(("SELECT", "WITH"))
    validate_query(sql, SCHEMA.allowed_relations)
