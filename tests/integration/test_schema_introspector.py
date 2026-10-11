import pytest
from sqlalchemy import Engine

from kontor.adapters.db.query_executor import PostgresQueryExecutor
from kontor.adapters.db.schema_introspector import PostgresSchemaIntrospector
from kontor.application.sql_validator import validate_query
from kontor.domain.errors import QueryExecutionError, UnsafeQueryError
from kontor.domain.schema import ForeignKey, SchemaInfo


@pytest.fixture(scope="module")
def schema(engine: Engine) -> SchemaInfo:
    return PostgresSchemaIntrospector(engine).introspect()


def test_lists_views_with_columns_and_types(schema: SchemaInfo) -> None:
    flows = next(relation for relation in schema.relations if relation.name == "v_flows")

    assert flows.kind == "view"
    assert [column.name for column in flows.columns] == [
        "transaction_id",
        "account_id",
        "currency",
        "booking_date",
        "year",
        "month",
        "counterparty_normalized",
        "amount",
        "uncategorized",
        "top_slug",
        "top_name",
        "sub_slug",
        "sub_name",
        "flow",
    ]
    types = {column.name: column.type for column in flows.columns}
    assert types["amount"] == "numeric(12,2)"
    assert types["booking_date"] == "date"


def test_lists_tables(schema: SchemaInfo) -> None:
    kinds = {relation.name: relation.kind for relation in schema.relations}

    assert kinds["transactions"] == "table"
    assert kinds == {
        "v_flows": "view",
        "transactions": "table",
        "accounts": "table",
        "categories": "table",
    }


def test_leaves_out_what_the_agent_role_cannot_read(schema: SchemaInfo) -> None:
    assert "alembic_version" not in schema.allowed_relations


def test_lists_foreign_keys(schema: SchemaInfo) -> None:
    assert ForeignKey("transactions", "account_id", "accounts", "id") in schema.foreign_keys
    assert ForeignKey("categories", "parent_slug", "categories", "slug") in schema.foreign_keys


def test_allowlist_drives_the_validator(schema: SchemaInfo) -> None:
    validate_query("SELECT * FROM v_flows", schema.allowed_relations)
    with pytest.raises(UnsafeQueryError, match="alembic_version"):
        validate_query("SELECT * FROM alembic_version", schema.allowed_relations)


def test_reads_column_comments(schema: SchemaInfo) -> None:
    columns = {
        (relation.name, column.name): column.comment
        for relation in schema.relations
        for column in relation.columns
    }

    assert "SUM(-amount)" in (columns[("v_flows", "amount")] or "")
    assert "never by flow" in (columns[("v_flows", "flow")] or "")
    assert "negative" in (columns[("transactions", "amount")] or "")
    assert columns[("transactions", "fingerprint")] is None


@pytest.mark.parametrize(
    "relation", ["imports", "categorization_events", "v_monthly_category_spending"]
)
def test_hidden_relations_are_rejected(schema: SchemaInfo, engine: Engine, relation: str) -> None:
    with pytest.raises(UnsafeQueryError, match=relation):
        validate_query(f"SELECT * FROM {relation}", schema.allowed_relations)
    with pytest.raises(QueryExecutionError, match="permission denied"):
        PostgresQueryExecutor(engine, 5, 10).execute(f"SELECT * FROM {relation}")
