"""What the agent knows about the database (CONTRACT §16.4): the notes plus the live schema."""

import hashlib
from datetime import date
from importlib.resources import files

from kontor.domain.reference import CategoryRef, ReferenceValues
from kontor.domain.schema import SchemaInfo


def load_notes() -> str:
    """The committed notes on what the data means; shipped inside the package."""
    return files("kontor").joinpath("agent_notes.md").read_text(encoding="utf-8")


def render_schema(schema: SchemaInfo) -> str:
    """One block per relation, then the foreign keys. Sorted, so the text and hash are stable."""
    blocks = []
    for relation in sorted(schema.relations, key=lambda relation: relation.name):
        columns = "\n".join(f"  {column.name} {column.type}" for column in relation.columns)
        blocks.append(f"{relation.kind} {relation.name}\n{columns}")
    keys = sorted(
        f"  {key.table}.{key.column} -> {key.ref_table}.{key.ref_column}"
        for key in schema.foreign_keys
    )
    if keys:
        blocks.append("foreign keys\n" + "\n".join(keys))
    return "\n\n".join(blocks)


def prompt_hash(system_prompt: str, notes: str, schema_text: str) -> str:
    """SHA-256 over everything the model is told, so eval results tie to a prompt version."""
    digest = hashlib.sha256()
    for part in (system_prompt, notes, schema_text):
        # Length-prefixed, so moving text from one part to the next changes the hash.
        encoded = part.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def render_reference(values: ReferenceValues) -> str:
    """The category tree and account names, so the model filters on values that exist."""
    children: dict[str, list[CategoryRef]] = {}
    for category in values.categories:
        if category.parent_slug is not None:
            children.setdefault(category.parent_slug, []).append(category)
    lines = [
        "# Categories",
        "",
        "Filter on these exact slugs; never guess a category name. In v_flows and the report "
        "views, `sub_slug` is the subcategory and `top_slug` its top-level category, so filter "
        "those columns directly. The categories table has no such columns and needs no join.",
        "",
    ]
    for top in values.categories:
        if top.parent_slug is not None:
            continue
        lines.append(f"- {top.slug}: {top.name} ({top.kind})")
        lines += [f"  - {sub.slug}: {sub.name}" for sub in children.get(top.slug, [])]
    lines += ["", "# Accounts", "", "Account names (`accounts.name`):", ""]
    lines += [f"- {name}" for name in values.accounts] or ["- (none yet)"]
    return "\n".join(lines)


def render_date_anchors(today: date) -> str:
    """Literal date ranges, so the model copies dates instead of computing them."""
    this_month = today.replace(day=1)
    ranges = [
        ("this month", this_month, _add_months(this_month, 1)),
        ("last month", _add_months(this_month, -1), this_month),
        ("the last 3 complete months", _add_months(this_month, -3), this_month),
        ("the last 6 complete months", _add_months(this_month, -6), this_month),
        ("the last 12 complete months", _add_months(this_month, -12), this_month),
        ("this year", date(today.year, 1, 1), date(today.year + 1, 1, 1)),
        ("last year", date(today.year - 1, 1, 1), date(today.year, 1, 1)),
    ]
    lines = [
        "# Dates",
        "",
        f"Today is {today.isoformat()}. For relative periods, filter `booking_date` with these "
        "ranges: the start is included, the end is not.",
        "",
    ]
    lines += [
        f"- {label}: booking_date >= '{start.isoformat()}' AND booking_date < '{end.isoformat()}'"
        for label, start, end in ranges
    ]
    return "\n".join(lines)


def _add_months(first_of_month: date, months: int) -> date:
    index = first_of_month.year * 12 + first_of_month.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)
