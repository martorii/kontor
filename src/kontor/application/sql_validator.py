"""Checks agent SQL before it runs (CONTRACT §16.3). Pure: parses, never executes.

The executor runs the original text, never sqlglot's re-rendered SQL, so a parser quirk cannot
change what runs. The read-only role (Step 24) stays the last line of defence; the reasons here
are written for the model, which gets them back to correct its query.
"""

from collections.abc import Iterator
from fnmatch import fnmatch

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from kontor.domain.errors import UnsafeQueryError

ALLOWED_SCHEMA = "public"

# Shell-style patterns, matched against lowercase function names.
DENIED_FUNCTIONS = (
    "pg_sleep*",
    "pg_read_*",
    "pg_ls_dir",
    "lo_*",
    "dblink*",
    "set_config",
    "pg_terminate_backend",
    "pg_cancel_backend",
    "pg_advisory*",
    "txid_*",
    "nextval",
    "setval",
    # These run SQL passed as a string, which the relation check cannot see.
    "query_to_xml*",
    "cursor_to_xml",
)

# Node types that must not appear anywhere in the tree, not just at the root: a CTE can hold
# `DELETE ... RETURNING`. DML covers INSERT, UPDATE, DELETE, MERGE and COPY; DDL covers CREATE.
# Command is sqlglot's fallback for statements it does not model (SET ROLE, DO, CALL, ...).
DENIED_NODES: tuple[type[exp.Expr], ...] = (
    exp.DML,
    exp.DDL,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
    exp.Grant,
    exp.Revoke,
    exp.Command,
    exp.Set,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
    exp.Comment,
    exp.Analyze,
)


def validate_query(sql: str, allowed_relations: frozenset[str]) -> None:
    """Accept exactly one SELECT over `allowed_relations`, or raise UnsafeQueryError.

    `allowed_relations` holds lowercase names of tables and views in `public`.
    """
    statement = _parse_single(sql)
    if not isinstance(statement, exp.Query):
        raise UnsafeQueryError(f"only SELECT queries are allowed, got {statement.key.upper()}")
    for node in statement.walk():
        _check_node(node)
    _check_relations(statement, allowed_relations)
    _check_functions(statement)


def _parse_single(sql: str) -> exp.Expr:
    try:
        parsed = sqlglot.parse(sql, read="postgres")
    except ParseError as exc:
        raise UnsafeQueryError(f"could not parse the SQL: {exc}") from exc
    statements = [statement for statement in parsed if statement is not None]
    if not statements:
        raise UnsafeQueryError("the query is empty")
    if len(statements) > 1:
        raise UnsafeQueryError(f"expected exactly one statement, got {len(statements)}")
    return statements[0]


def _check_node(node: exp.Expr) -> None:
    if isinstance(node, exp.Lock):
        raise UnsafeQueryError("locking clauses (FOR UPDATE, FOR SHARE) are not allowed")
    if isinstance(node, DENIED_NODES):
        raise UnsafeQueryError(f"{node.key.upper()} is not allowed")
    if isinstance(node, exp.Select) and node.args.get("into") is not None:
        raise UnsafeQueryError("SELECT INTO is not allowed")


def _check_relations(statement: exp.Expr, allowed_relations: frozenset[str]) -> None:
    cte_names = {_identifier(cte.args["alias"].this) for cte in statement.find_all(exp.CTE)}
    for table in statement.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            continue  # a table function such as generate_series; _check_functions covers it
        name = _identifier(table.this)
        if table.args.get("catalog") is not None:
            raise UnsafeQueryError(f'relation "{table.sql(dialect="postgres")}" is not allowed')
        schema = table.args.get("db")
        if schema is not None:
            schema_name = _identifier(schema)
            if schema_name != ALLOWED_SCHEMA:
                raise UnsafeQueryError(f'schema "{schema_name}" is not allowed')
        elif name in cte_names:
            continue
        if name not in allowed_relations:
            raise UnsafeQueryError(f'relation "{name}" is not allowed')


def _check_functions(statement: exp.Expr) -> None:
    for name in _function_names(statement):
        if any(fnmatch(name, pattern) for pattern in DENIED_FUNCTIONS):
            raise UnsafeQueryError(f'function "{name}" is not allowed')


def _function_names(statement: exp.Expr) -> Iterator[str]:
    for func in statement.find_all(exp.Func):
        if isinstance(func, exp.Anonymous):
            yield func.name.lower()
        else:
            yield func.sql_name().lower()


def _identifier(node: exp.Expr) -> str:
    """Postgres folds unquoted identifiers to lowercase; quoted ones keep their case."""
    if isinstance(node, exp.Identifier) and node.quoted:
        return node.name
    return node.name.lower()
