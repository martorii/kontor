from itertools import groupby
from typing import Literal

from sqlalchemy import Engine, text

from kontor.adapters.db.query_executor import AGENT_ROLE
from kontor.domain.schema import Column, ForeignKey, Relation, SchemaInfo

# Tables and views in `public` the agent role may SELECT, with their columns in table order.
# The role's grants (Step 24 migration) decide what is listed, so `alembic_version` drops out.
RELATIONS_SQL = """
SELECT c.relname, c.relkind, a.attname, format_type(a.atttypid, a.atttypmod)
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
WHERE n.nspname = 'public'
  AND c.relkind IN ('r', 'p', 'v', 'm')
  AND has_table_privilege(:role, c.oid, 'SELECT')
ORDER BY c.relname, a.attnum
"""

# Single-column foreign keys between relations the agent role can read.
FOREIGN_KEYS_SQL = """
SELECT src.relname, src_col.attname, dst.relname, dst_col.attname
FROM pg_constraint con
JOIN pg_class src ON src.oid = con.conrelid
JOIN pg_namespace n ON n.oid = src.relnamespace
JOIN pg_class dst ON dst.oid = con.confrelid
JOIN pg_attribute src_col ON src_col.attrelid = con.conrelid AND src_col.attnum = con.conkey[1]
JOIN pg_attribute dst_col ON dst_col.attrelid = con.confrelid AND dst_col.attnum = con.confkey[1]
WHERE con.contype = 'f'
  AND n.nspname = 'public'
  AND array_length(con.conkey, 1) = 1
  AND has_table_privilege(:role, src.oid, 'SELECT')
  AND has_table_privilege(:role, dst.oid, 'SELECT')
ORDER BY src.relname, src_col.attname
"""

KINDS: dict[str, Literal["table", "view"]] = {"r": "table", "p": "table", "v": "view", "m": "view"}


class PostgresSchemaIntrospector:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def introspect(self) -> SchemaInfo:
        with self._engine.connect() as conn:
            column_rows = conn.execute(text(RELATIONS_SQL), {"role": AGENT_ROLE}).all()
            key_rows = conn.execute(text(FOREIGN_KEYS_SQL), {"role": AGENT_ROLE}).all()
        relations = tuple(
            Relation(
                name=name,
                kind=KINDS[kind],
                columns=tuple(Column(name=row[2], type=row[3]) for row in rows),
            )
            for (name, kind), rows in groupby(column_rows, key=lambda row: (row[0], row[1]))
        )
        foreign_keys = tuple(
            ForeignKey(table=row[0], column=row[1], ref_table=row[2], ref_column=row[3])
            for row in key_rows
        )
        return SchemaInfo(relations=relations, foreign_keys=foreign_keys)
