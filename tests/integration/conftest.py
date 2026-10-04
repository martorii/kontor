import os
import uuid
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from kontor.api.app import create_app
from kontor.config import Settings

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """A fresh, migrated database, created next to the configured one and dropped afterwards.

    Never touches the configured database itself, so a developer's data is safe.
    """
    base = make_url(os.environ.get("DATABASE_URL") or Settings().database_url)
    name = f"kontor_test_{uuid.uuid4().hex[:8]}"
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    except OperationalError as exc:
        admin.dispose()
        if os.environ.get("CI"):
            raise
        pytest.skip(f"Postgres not reachable: {exc.orig}")
    url = base.set(database=name).render_as_string(hide_password=False)
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
        yield url
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture(scope="session")
def engine(postgres_url: str) -> Iterator[Engine]:
    engine = create_engine(postgres_url)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    """A session whose work is rolled back after each test."""
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(connection, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()


@pytest.fixture
def make_client(
    postgres_url: str, engine: Engine, tmp_path: Path
) -> Iterator[Callable[[str | None], TestClient]]:
    """Build API clients on the test database. Committed data is wiped after each test.

    Pass rules YAML text to use custom rules, or None for config/rules.example.yaml. The app
    startup (rules load and category sync) runs for every client.
    """
    stack = ExitStack()

    def factory(rules_yaml: str | None = None) -> TestClient:
        rules_path = ROOT / "config" / "rules.example.yaml"
        if rules_yaml is not None:
            rules_path = tmp_path / "rules.yaml"
            rules_path.write_text(rules_yaml)
        settings = Settings(database_url=postgres_url, rules_path=str(rules_path))
        return stack.enter_context(TestClient(create_app(settings)))

    yield factory
    stack.close()
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE categorization_events, transactions, imports, accounts, categories "
                "RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture
def client(make_client: Callable[[str | None], TestClient]) -> TestClient:
    return make_client(None)
