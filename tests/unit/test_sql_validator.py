import pytest

from kontor.application.sql_validator import validate_query
from kontor.domain.errors import UnsafeQueryError

ALLOWED = frozenset(
    {"accounts", "transactions", "categories", "v_flows", "v_merchant_spending", "t1", "t2"}
)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM accounts",
        "select id, name from accounts;",
        "SELECT * FROM public.v_flows",
        "SELECT * FROM Accounts",
        "WITH monthly AS (SELECT month, SUM(amount) AS s FROM v_flows GROUP BY month) "
        "SELECT * FROM monthly ORDER BY month",
        "SELECT name FROM accounts UNION SELECT slug FROM categories",
        "SELECT name FROM accounts INTERSECT SELECT name FROM accounts",
        "SELECT * FROM transactions WHERE account_id IN (SELECT id FROM accounts)",
        "SELECT * FROM (SELECT id FROM accounts) AS a",
        "SELECT counterparty_normalized, SUM(-amount) OVER (PARTITION BY month) FROM v_flows",
        "SELECT n FROM generate_series(1, 12) AS n",
        "SELECT * FROM accounts a, LATERAL generate_series(1, 2) AS g",
        "SELECT * FROM transactions WHERE purpose LIKE '%rent%'",
        "SELECT 'a:b', lower(name), date_trunc('month', booking_date) FROM transactions",
        "SELECT * FROM t1 JOIN public.t2 USING (id)",
        "SELECT * FROM v_merchant_spending ORDER BY spent DESC LIMIT 10",
        "SELECT current_date, now()",
        "(SELECT 1)",
        "SELECT * FROM accounts /* ; DROP TABLE accounts */",
        "SELECT * FROM pg_catalog.generate_series(1, 2) AS n",
    ],
)
def test_accepts_read_only_selects(sql: str) -> None:
    validate_query(sql, ALLOWED)


@pytest.mark.parametrize(
    ("sql", "reason"),
    [
        ("INSERT INTO accounts (name) VALUES ('x')", "only SELECT queries are allowed, got INSERT"),
        ("UPDATE accounts SET name = 'x'", "only SELECT queries are allowed, got UPDATE"),
        ("DELETE FROM accounts", "only SELECT queries are allowed, got DELETE"),
        ("MERGE INTO accounts USING t1 ON true WHEN MATCHED THEN DELETE", "got MERGE"),
        ("CREATE TABLE x (id int)", "got CREATE"),
        ("DROP VIEW v_flows", "got DROP"),
        ("ALTER TABLE accounts ADD COLUMN x int", "got ALTER"),
        ("TRUNCATE accounts", "got TRUNCATETABLE"),
        ("GRANT SELECT ON accounts TO public", "got GRANT"),
        (
            "WITH gone AS (DELETE FROM accounts RETURNING *) SELECT * FROM gone",
            "DELETE is not allowed",
        ),
        ("SELECT 1; SELECT 2", "expected exactly one statement, got 2"),
        ("SELECT 1; DROP TABLE accounts", "expected exactly one statement, got 2"),
        ("SELECT * INTO copy_of_accounts FROM accounts", "SELECT INTO is not allowed"),
        ("SELECT * FROM accounts FOR UPDATE", "locking clauses"),
        ("SELECT * FROM accounts FOR SHARE", "locking clauses"),
        ("SET ROLE kontor", "got COMMAND"),
        ("RESET ROLE", "got COMMAND"),
        ("COPY accounts TO STDOUT", "got COPY"),
        ("DO $$ BEGIN END $$", "got COMMAND"),
        ("CALL refresh()", "got COMMAND"),
        ("SELECT * FROM pg_catalog.pg_roles", 'schema "pg_catalog" is not allowed'),
        ("SELECT * FROM information_schema.tables", 'schema "information_schema" is not allowed'),
        ("SELECT * FROM alembic_version", 'relation "alembic_version" is not allowed'),
        ("SELECT * FROM pg_roles", 'relation "pg_roles" is not allowed'),
        ('SELECT * FROM "Accounts"', 'relation "Accounts" is not allowed'),
        ("SELECT * FROM otherdb.public.accounts", "is not allowed"),
        ("SELECT pg_sleep(20)", 'function "pg_sleep" is not allowed'),
        ("SELECT pg_sleep_for('1 minute')", 'function "pg_sleep_for" is not allowed'),
        ("SELECT pg_read_file('/etc/passwd')", 'function "pg_read_file" is not allowed'),
        ("SELECT * FROM dblink('host=x', 'SELECT 1') AS t(x int)", 'function "dblink"'),
        ("SELECT set_config('role', 'x', false)", 'function "set_config" is not allowed'),
        ("SELECT query_to_xml('SELECT 1', true, true, '')", 'function "query_to_xml"'),
        ("SELECT pg_advisory_lock(1)", 'function "pg_advisory_lock" is not allowed'),
        ("SELECT * FROM accounts WHERE id = (SELECT pg_sleep(5))", 'function "pg_sleep"'),
        ("SELECT pg_catalog.pg_sleep(1)", 'function "pg_sleep" is not allowed'),
        ('SELECT "pg_sleep"(1)', 'function "pg_sleep" is not allowed'),
        ("SELECT PG_SLEEP(1)", 'function "pg_sleep" is not allowed'),
        ("SELECT nextval('accounts_id_seq')", 'function "nextval" is not allowed'),
        (
            "WITH x AS (SELECT * FROM alembic_version) SELECT * FROM x",
            'relation "alembic_version" is not allowed',
        ),
        ("EXPLAIN ANALYZE SELECT 1", "got COMMAND"),
        ("garbage text here", "could not parse the SQL"),
        ("", "the query is empty"),
        ("VALUES (1)", "only SELECT queries are allowed, got VALUES"),
    ],
)
def test_rejects_with_a_reason(sql: str, reason: str) -> None:
    with pytest.raises(UnsafeQueryError) as excinfo:
        validate_query(sql, ALLOWED)
    assert reason in str(excinfo.value)
