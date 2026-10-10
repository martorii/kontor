from kontor.application.agent_context import load_notes, prompt_hash, render_schema
from kontor.domain.schema import Column, ForeignKey, Relation, SchemaInfo

SCHEMA = SchemaInfo(
    relations=(
        Relation("v_flows", "view", (Column("amount", "numeric(12,2)"),)),
        Relation("accounts", "table", (Column("id", "bigint"), Column("name", "text"))),
    ),
    foreign_keys=(ForeignKey("transactions", "account_id", "accounts", "id"),),
)


def test_notes_load_from_the_package() -> None:
    notes = load_notes()

    assert "Negative amounts are outflows" in notes
    assert "v_flows" in notes


def test_render_schema_lists_relations_sorted_with_types() -> None:
    assert render_schema(SCHEMA) == (
        "table accounts\n"
        "  id bigint\n"
        "  name text\n"
        "\n"
        "view v_flows\n"
        "  amount numeric(12,2)\n"
        "\n"
        "foreign keys\n"
        "  transactions.account_id -> accounts.id"
    )


def test_render_schema_ignores_input_order() -> None:
    reversed_schema = SchemaInfo(SCHEMA.relations[::-1], SCHEMA.foreign_keys)

    assert render_schema(reversed_schema) == render_schema(SCHEMA)


def test_allowed_relations_are_the_relation_names() -> None:
    assert SCHEMA.allowed_relations == frozenset({"v_flows", "accounts"})


def test_prompt_hash_is_stable() -> None:
    assert prompt_hash("system", "notes", "schema") == prompt_hash("system", "notes", "schema")


def test_prompt_hash_changes_with_every_part() -> None:
    base = prompt_hash("system", "notes", "schema")

    assert prompt_hash("system!", "notes", "schema") != base
    assert prompt_hash("system", "notes!", "schema") != base
    assert prompt_hash("system", "notes", "schema!") != base


def test_prompt_hash_tells_parts_apart() -> None:
    assert prompt_hash("ab", "c", "") != prompt_hash("a", "bc", "")
