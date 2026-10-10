from datetime import date

from kontor.application.agent_context import (
    load_notes,
    prompt_hash,
    render_date_anchors,
    render_reference,
    render_schema,
)
from kontor.domain.reference import CategoryRef, ReferenceValues
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


def test_render_reference_lists_the_tree_and_accounts() -> None:
    values = ReferenceValues(
        categories=(
            CategoryRef("food", "Food", None, "expense"),
            CategoryRef("food.coffee", "Coffee & bakery", "food", None),
            CategoryRef("food.groceries", "Groceries", "food", None),
            CategoryRef("income", "Income", None, "income"),
        ),
        accounts=("Gemeinschaftskonto", "Girokonto"),
    )

    text = render_reference(values)

    assert (
        "- food: Food (expense)\n"
        "  - food.coffee: Coffee & bakery\n"
        "  - food.groceries: Groceries\n"
        "- income: Income (income)\n"
    ) in text
    assert "- Gemeinschaftskonto\n- Girokonto" in text


def test_render_reference_without_accounts() -> None:
    assert "- (none yet)" in render_reference(ReferenceValues((), ()))


def test_date_anchors_mid_year() -> None:
    text = render_date_anchors(date(2026, 10, 10))

    assert "Today is 2026-10-10." in text
    assert "- this month: booking_date >= '2026-10-01' AND booking_date < '2026-11-01'" in text
    assert "- last month: booking_date >= '2026-09-01' AND booking_date < '2026-10-01'" in text
    assert "- the last 3 complete months: booking_date >= '2026-07-01'" in text
    assert "- the last 12 complete months: booking_date >= '2025-10-01'" in text
    assert "- this year: booking_date >= '2026-01-01' AND booking_date < '2027-01-01'" in text
    assert "- last year: booking_date >= '2025-01-01' AND booking_date < '2026-01-01'" in text


def test_date_anchors_cross_the_year_in_january_and_december() -> None:
    january = render_date_anchors(date(2027, 1, 31))
    december = render_date_anchors(date(2026, 12, 1))

    assert "- last month: booking_date >= '2026-12-01' AND booking_date < '2027-01-01'" in january
    assert "- this month: booking_date >= '2026-12-01' AND booking_date < '2027-01-01'" in december
