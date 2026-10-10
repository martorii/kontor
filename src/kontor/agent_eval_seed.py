"""Synthetic data for the agent evaluation (CONTRACT §16.9). Never used on the real database.

Deterministic for a given `today`: twelve months of transactions up to `today`, so relative
questions ("last month", "this year") always have data. Merchants, names and IBANs are fake.
The category tree is `config/rules.example.yaml`, which the golden set's reference SQL assumes.
"""

import hashlib
import random
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Engine, insert
from sqlalchemy.orm import sessionmaker

from kontor.adapters.db.models import Account, Import, Transaction
from kontor.adapters.db.uow import SqlUnitOfWork
from kontor.adapters.rules.yaml_source import YamlRulesSource
from kontor.application.category_sync import sync_categories
from kontor.domain.normalization import normalize_counterparty

EXAMPLE_RULES = Path(__file__).resolve().parents[2] / "config" / "rules.example.yaml"
SEED = 20261010

CHECKING = 1  # account ids as inserted below
JOINT = 2


@dataclass(frozen=True, slots=True)
class _Row:
    account: int
    booking_date: date
    amount: Decimal
    counterparty: str
    purpose: str
    category: str | None
    source: str | None


# (category, merchants, transactions per month (min, max), amount range in EUR)
_VARIABLE: list[tuple[str, list[str], tuple[int, int], tuple[int, int]]] = [
    (
        "food.groceries",
        ["FRISCHMARKT", "BIOLADEN GRUENKERN", "DISCOUNTER NORD"],
        (6, 10),
        (15, 120),
    ),
    ("food.restaurants", ["TRATTORIA BEISPIEL", "BURGERHAUS MUSTER"], (2, 4), (18, 75)),
    ("food.coffee", ["BAECKEREI KORN"], (3, 6), (3, 9)),
    ("transport.fuel", ["TANKSTELLE WEST"], (1, 2), (50, 90)),
    ("health.pharmacy", ["APOTHEKE AM MARKT"], (0, 2), (8, 40)),
    ("shopping.clothing", ["MODEHAUS MUSTER"], (0, 2), (25, 140)),
    ("kids.toys", ["SPIELWAREN KUNTERBUNT"], (0, 1), (10, 60)),
    ("cash.withdrawals", ["GELDAUTOMAT BEISPIELBANK"], (1, 1), (100, 200)),
]

# (day, account, amount, counterparty, purpose, category)
_MONTHLY: list[tuple[int, int, str, str, str, str]] = [
    (1, CHECKING, "3200.00", "BEISPIEL ARBEITGEBER GMBH", "Gehalt", "income.salary"),
    (2, CHECKING, "-500.00", "EIGENES GEMEINSCHAFTSKONTO", "Umbuchung", "transfer.internal"),
    (2, JOINT, "500.00", "EIGENES GIROKONTO", "Umbuchung", "transfer.internal"),
    (2, CHECKING, "-200.00", "BEISPIEL SPARPLAN", "Sparrate", "savings.deposits"),
    (3, CHECKING, "-1150.00", "MUSTER HAUSVERWALTUNG", "Miete", "housing.rent"),
    (5, JOINT, "-320.00", "KITA SONNENSCHEIN", "Betreuung", "kids.daycare"),
    (10, CHECKING, "-39.99", "NETZ TELEKOM BEISPIEL", "Internet", "housing.internet-phone"),
    (12, JOINT, "255.00", "FAMILIENKASSE", "Kindergeld", "income.child-benefit"),
    (15, CHECKING, "-85.00", "STADTWERKE BEISPIELSTADT", "Strom und Gas", "housing.utilities"),
    (18, CHECKING, "-58.00", "VERKEHRSVERBUND BEISPIEL", "Monatsticket", "transport.public"),
    (20, CHECKING, "-12.99", "STREAMFLIX", "Abo", "leisure.subscriptions"),
]

_UNKNOWN = ["HAENDLER ALPHA", "HAENDLER BETA", "ONLINESHOP GAMMA"]


def generate(today: date) -> list[_Row]:
    rng = random.Random(SEED)
    rows: list[_Row] = []

    def add(
        account: int,
        booking: date,
        amount: Decimal,
        counterparty: str,
        purpose: str,
        category: str | None,
        source: str | None,
    ) -> None:
        if booking <= today:  # the current month runs only up to today
            rows.append(_Row(account, booking, amount, counterparty, purpose, category, source))

    for year, month in _months(today):
        last_day = _days_in_month(year, month)
        for day, account, fixed, counterparty, purpose, category in _MONTHLY:
            add(
                account,
                date(year, month, day),
                Decimal(fixed),
                counterparty,
                purpose,
                category,
                "rule",
            )
        for category, merchants, (low, high), (min_eur, max_eur) in _VARIABLE:
            for _ in range(rng.randint(low, high)):
                booking = date(year, month, rng.randint(1, last_day))
                cents = rng.randint(min_eur * 100, max_eur * 100)
                source = rng.choice(["rule", "rule", "llm", "manual"])
                account = rng.choice([CHECKING, CHECKING, JOINT])
                merchant = rng.choice(merchants)
                add(account, booking, -Decimal(cents) / 100, merchant, "Einkauf", category, source)
        if month % 3 == 0:  # a clothing refund every quarter: a positive expense
            add(
                CHECKING,
                date(year, month, 25),
                Decimal("29.95"),
                "MODEHAUS MUSTER",
                "Erstattung",
                "shopping.clothing",
                "manual",
            )
        for _ in range(rng.randint(1, 3)):
            booking = date(year, month, rng.randint(1, last_day))
            cents = rng.randint(500, 9000)
            add(CHECKING, booking, -Decimal(cents) / 100, rng.choice(_UNKNOWN), "Kauf", None, None)
    return rows


def seed(engine: Engine, today: date) -> int:
    """Load the category tree and the synthetic data into an empty database. Returns the count."""
    sync_categories(
        lambda: SqlUnitOfWork(sessionmaker(engine)),
        YamlRulesSource(EXAMPLE_RULES).load().categories,
    )
    rows = generate(today)
    with engine.begin() as conn:
        conn.execute(
            insert(Account),
            [
                {
                    "id": CHECKING,
                    "name": "Girokonto",
                    "bank": "Beispielbank",
                    "iban": "DE00000000000000000001",
                    "currency": "EUR",
                    "account_type": "checking",
                    "parser_format": "synthetic",
                },
                {
                    "id": JOINT,
                    "name": "Gemeinschaftskonto",
                    "bank": "Beispielbank",
                    "iban": "DE00000000000000000002",
                    "currency": "EUR",
                    "account_type": "checking",
                    "parser_format": "synthetic",
                },
            ],
        )
        conn.execute(
            insert(Import),
            [
                {
                    "id": account,
                    "account_id": account,
                    "file_name": f"synthetic-{account}.csv",
                    "file_hash": hashlib.sha256(f"synthetic-{account}".encode()).hexdigest(),
                    "status": "completed",
                    "new_count": sum(r.account == account for r in rows),
                }
                for account in (CHECKING, JOINT)
            ],
        )
        conn.execute(
            insert(Transaction),
            [
                {
                    "account_id": row.account,
                    "import_id": row.account,
                    "booking_date": row.booking_date,
                    "value_date": row.booking_date,
                    "amount": row.amount,
                    "currency": "EUR",
                    "counterparty_raw": row.counterparty,
                    "counterparty_normalized": normalize_counterparty(row.counterparty),
                    "counterparty_iban": None,
                    "purpose": row.purpose,
                    "fingerprint": hashlib.sha256(f"{index}".encode()).hexdigest(),
                    "raw_row": {},
                    "category_slug": row.category,
                    "category_source": row.source,
                }
                for index, row in enumerate(rows)
            ],
        )
        # Explicit ids above leave the sequences behind; keep them usable for later inserts.
        for table in ("accounts", "imports"):
            conn.exec_driver_sql(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"(SELECT MAX(id) FROM {table}))"
            )
    return len(rows)


def _months(today: date) -> list[tuple[int, int]]:
    """The twelve months before today's month, then today's month."""
    months = []
    year, month = today.year, today.month
    for _ in range(13):
        months.append((year, month))
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    return list(reversed(months))


def _days_in_month(year: int, month: int) -> int:
    following = date(year + month // 12, month % 12 + 1, 1)
    return (following - date(year, month, 1)).days
