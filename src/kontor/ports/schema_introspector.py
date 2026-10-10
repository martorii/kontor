from typing import Protocol

from kontor.domain.schema import SchemaInfo


class SchemaIntrospector(Protocol):
    def introspect(self) -> SchemaInfo:
        """The tables, views, columns and foreign keys the agent role can SELECT."""
        ...
