"""What the agent knows about the database (CONTRACT §16.4): the notes plus the live schema."""

import hashlib
from importlib.resources import files

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
