import pytest
from sqlalchemy import Engine

from kontor.adapters.db.schema_introspector import PostgresSchemaIntrospector
from kontor.application.sql_validator import validate_query
from kontor.domain.errors import UnsafeQueryError
from kontor.domain.schema import Column, ForeignKey, SchemaInfo


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
    assert Column("amount", "numeric(12,2)") in flows.columns
    assert Column("booking_date", "date") in flows.columns


def test_lists_tables(schema: SchemaInfo) -> None:
    kinds = {relation.name: relation.kind for relation in schema.relations}

    assert kinds["transactions"] == "table"
    assert kinds["v_merchant_spending"] == "view"
    assert {"accounts", "imports", "categories", "categorization_events"} <= kinds.keys()


def test_leaves_out_what_the_agent_role_cannot_read(schema: SchemaInfo) -> None:
    assert "alembic_version" not in schema.allowed_relations


def test_lists_foreign_keys(schema: SchemaInfo) -> None:
    assert ForeignKey("transactions", "account_id", "accounts", "id") in schema.foreign_keys
    assert ForeignKey("categories", "parent_slug", "categories", "slug") in schema.foreign_keys


def test_allowlist_drives_the_validator(schema: SchemaInfo) -> None:
    validate_query("SELECT * FROM v_flows", schema.allowed_relations)
    with pytest.raises(UnsafeQueryError, match="alembic_version"):
        validate_query("SELECT * FROM alembic_version", schema.allowed_relations)
