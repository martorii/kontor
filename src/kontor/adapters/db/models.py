from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

MONEY = Numeric(12, 2)


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, comment="Account name as the user sees it.")
    bank: Mapped[str] = mapped_column(Text)
    iban: Mapped[str] = mapped_column(String(34), unique=True)
    currency: Mapped[str] = mapped_column(String(3))
    account_type: Mapped[str] = mapped_column(Text)
    parser_format: Mapped[str] = mapped_column(Text)


class Import(Base):
    __tablename__ = "imports"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'completed', 'failed')", name="status_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    file_name: Mapped[str] = mapped_column(Text)
    file_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(Text)
    new_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    rule_matched_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    llm_matched_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    uncategorized_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint("kind IN ('expense', 'income', 'transfer', 'savings')", name="kind_valid"),
        CheckConstraint("(parent_slug IS NULL) = (kind IS NOT NULL)", name="kind_top_level_only"),
    )

    slug: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
        comment="Top-level slug such as food, or subcategory slug such as food.groceries.",
    )
    parent_slug: Mapped[str | None] = mapped_column(
        ForeignKey("categories.slug"),
        comment="Top-level category of a subcategory; NULL for top-level categories.",
    )
    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str | None] = mapped_column(
        Text, comment="expense, income, transfer or savings; set on top-level categories only."
    )


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("account_id", "fingerprint", name="uq_transactions_account_fingerprint"),
        CheckConstraint(
            "category_source IN ('rule', 'llm', 'manual')", name="category_source_valid"
        ),
        CheckConstraint(
            "(category_slug IS NULL) = (category_source IS NULL)", name="category_with_source"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    import_id: Mapped[int] = mapped_column(ForeignKey("imports.id"))
    booking_date: Mapped[date] = mapped_column(
        Date, comment="Date the bank booked the transaction; use it for date filters."
    )
    value_date: Mapped[date | None] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(
        MONEY, comment="Signed: negative is money leaving the account, positive is money coming in."
    )
    currency: Mapped[str] = mapped_column(String(3))
    counterparty_raw: Mapped[str] = mapped_column(Text)
    counterparty_normalized: Mapped[str] = mapped_column(
        Text, comment="Merchant or person, uppercase, without store numbers; match with ILIKE."
    )
    counterparty_iban: Mapped[str | None] = mapped_column(String(34))
    purpose: Mapped[str] = mapped_column(
        Text, comment="Free-text payment reference; match with ILIKE."
    )
    fingerprint: Mapped[str] = mapped_column(String(64))
    # Any: the raw bank CSV row is free-form JSON that differs per bank format.
    raw_row: Mapped[dict[str, Any]] = mapped_column(JSONB)
    category_slug: Mapped[str | None] = mapped_column(
        ForeignKey("categories.slug"),
        comment="Subcategory slug (categories.slug), or NULL when uncategorized.",
    )
    category_source: Mapped[str | None] = mapped_column(
        Text, comment="Who set the category: rule, llm or manual; NULL when uncategorized."
    )


class CategorizationEvent(Base):
    __tablename__ = "categorization_events"
    __table_args__ = (CheckConstraint("source IN ('rule', 'llm', 'manual')", name="source_valid"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"))
    category_slug: Mapped[str | None] = mapped_column(ForeignKey("categories.slug"))
    source: Mapped[str] = mapped_column(Text)
    applied: Mapped[bool] = mapped_column(Boolean)
    rule_id: Mapped[str | None] = mapped_column(Text)
    rules_hash: Mapped[str | None] = mapped_column(String(64))
    model_name: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
