from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kontor.adapters.db.models import (
    Account,
    CategorizationEvent,
    Category,
    Import,
    Transaction,
)

ROOT = Path(__file__).resolve().parents[2]


def _account() -> Account:
    return Account(
        name="Test account",
        bank="Testbank",
        iban="DE00000000000000000000",
        currency="EUR",
        account_type="checking",
        parser_format="test",
    )


def _transaction(account: Account, import_: Import, **overrides: object) -> Transaction:
    fields: dict[str, object] = {
        "booking_date": date(2026, 1, 15),
        "amount": Decimal("-12.34"),
        "currency": "EUR",
        "counterparty_raw": "Example Shop 123",
        "counterparty_normalized": "EXAMPLE SHOP",
        "purpose": "Groceries",
        "fingerprint": "f" * 64,
        "raw_row": {"Buchungsdatum": "15.01.26"},
    }
    fields.update(overrides)
    return Transaction(import_id=import_.id, account_id=account.id, **fields)


def test_insert_and_read_one_row_per_table(session: Session) -> None:
    account = _account()
    parent = Category(slug="food", name="Food", kind="expense")
    child = Category(slug="food.groceries", parent_slug="food", name="Groceries")
    session.add_all([account, parent, child])
    session.flush()
    import_ = Import(
        account_id=account.id, file_name="export.csv", file_hash="a" * 64, status="completed"
    )
    session.add(import_)
    session.flush()
    transaction = Transaction(
        account_id=account.id,
        import_id=import_.id,
        booking_date=date(2026, 1, 15),
        value_date=date(2026, 1, 16),
        amount=Decimal("-12.34"),
        currency="EUR",
        counterparty_raw="Example Shop 123",
        counterparty_normalized="EXAMPLE SHOP",
        counterparty_iban="DE11111111111111111111",
        purpose="Groceries",
        fingerprint="f" * 64,
        raw_row={"Buchungsdatum": "15.01.26", "Betrag": "-12,34"},
        category_slug="food.groceries",
        category_source="rule",
    )
    session.add(transaction)
    session.flush()
    event = CategorizationEvent(
        transaction_id=transaction.id,
        category_slug="food.groceries",
        source="rule",
        applied=True,
        rule_id="groceries-1",
        rules_hash="b" * 64,
        confidence=Decimal("0.875"),
    )
    session.add(event)
    session.flush()
    session.expire_all()

    assert session.scalars(select(Account)).one().iban == "DE00000000000000000000"
    assert {c.slug for c in session.scalars(select(Category))} == {"food", "food.groceries"}
    assert session.scalars(select(Import)).one().new_count == 0
    stored = session.scalars(select(Transaction)).one()
    assert stored.amount == Decimal("-12.34")
    assert stored.raw_row["Betrag"] == "-12,34"
    read_event = session.scalars(select(CategorizationEvent)).one()
    assert read_event.confidence == Decimal("0.875")
    assert isinstance(read_event.created_at, datetime)
    assert read_event.created_at.tzinfo is not None
    assert read_event.created_at <= datetime.now(UTC)


def test_fingerprint_is_unique_per_account(session: Session) -> None:
    account = _account()
    session.add(account)
    session.flush()
    import_ = Import(
        account_id=account.id, file_name="export.csv", file_hash="a" * 64, status="completed"
    )
    session.add(import_)
    session.flush()
    session.add(_transaction(account, import_))
    session.flush()

    with pytest.raises(IntegrityError), session.begin_nested():
        session.add(_transaction(account, import_))
        session.flush()


def test_category_requires_source(session: Session) -> None:
    account = _account()
    session.add_all([account, Category(slug="food", name="Food", kind="expense")])
    session.flush()
    import_ = Import(
        account_id=account.id, file_name="export.csv", file_hash="a" * 64, status="completed"
    )
    session.add(import_)
    session.flush()

    with pytest.raises(IntegrityError), session.begin_nested():
        session.add(_transaction(account, import_, category_slug="food"))
        session.flush()


def test_subcategory_has_no_kind(session: Session) -> None:
    session.add(Category(slug="food", name="Food", kind="expense"))
    session.flush()

    with pytest.raises(IntegrityError), session.begin_nested():
        session.add(Category(slug="food.x", parent_slug="food", name="X", kind="expense"))
        session.flush()


def test_downgrade_and_upgrade_roundtrip(postgres_url: str) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    command.downgrade(config, "base")
    command.upgrade(config, "head")
