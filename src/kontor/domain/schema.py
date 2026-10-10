from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class Column:
    """A column as Postgres renders its type, e.g. `numeric(12,2)` or `date`."""

    name: str
    type: str


@dataclass(frozen=True, slots=True)
class Relation:
    name: str
    kind: Literal["table", "view"]
    columns: tuple[Column, ...]


@dataclass(frozen=True, slots=True)
class ForeignKey:
    table: str
    column: str
    ref_table: str
    ref_column: str


@dataclass(frozen=True, slots=True)
class SchemaInfo:
    """What the agent role can read (CONTRACT §16.4)."""

    relations: tuple[Relation, ...]
    foreign_keys: tuple[ForeignKey, ...]

    @property
    def allowed_relations(self) -> frozenset[str]:
        """The validator allowlist (§16.3): exactly the relations the agent sees."""
        return frozenset(relation.name for relation in self.relations)
