from collections import Counter
from collections.abc import Mapping, Sequence
from decimal import Decimal

from sqlalchemy import func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kontor.adapters.db import models
from kontor.domain.account import Account, NewAccount
from kontor.domain.errors import (
    AccountNotFoundError,
    DuplicateIbanError,
    TransactionNotFoundError,
)
from kontor.domain.imports import ImportCounts, ImportRecord
from kontor.domain.llm import LLMOutcome
from kontor.domain.recategorization import Candidate, Change
from kontor.domain.reports import (
    CategorySpendingRow,
    ExplorerPage,
    ExplorerTransaction,
    IncomeExpensesRow,
    MerchantRow,
    TransactionFilter,
)
from kontor.domain.review import (
    ManualOverride,
    Suggestion,
    UncategorizedPage,
    UncategorizedTransaction,
)
from kontor.domain.rules import CategoryDef
from kontor.domain.transaction import PreparedTransaction, Transaction


def _account(row: models.Account) -> Account:
    return Account(
        id=row.id,
        name=row.name,
        bank=row.bank,
        iban=row.iban,
        currency=row.currency,
        account_type=row.account_type,
        parser_format=row.parser_format,
    )


def _candidate(row: models.Transaction, iban: str) -> Candidate:
    return Candidate(
        transaction_id=row.id,
        account_iban=iban,
        prepared=PreparedTransaction(
            transaction=Transaction(
                booking_date=row.booking_date,
                value_date=row.value_date,
                amount=row.amount,
                currency=row.currency,
                counterparty=row.counterparty_raw,
                counterparty_iban=row.counterparty_iban,
                purpose=row.purpose,
            ),
            counterparty_normalized=row.counterparty_normalized,
            fingerprint=row.fingerprint,
        ),
        category_slug=row.category_slug,
        category_source=row.category_source,
    )


def _import_record(row: models.Import) -> ImportRecord:
    return ImportRecord(
        id=row.id,
        account_id=row.account_id,
        file_name=row.file_name,
        file_hash=row.file_hash,
        status=row.status,
        created_at=row.created_at,
        counts=ImportCounts(
            new=row.new_count,
            duplicates=row.duplicate_count,
            rule_matched=row.rule_matched_count,
            llm_matched=row.llm_matched_count,
            uncategorized=row.uncategorized_count,
        ),
    )


class SqlAccountRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, account_id: int) -> Account | None:
        row = self._session.get(models.Account, account_id)
        return _account(row) if row else None

    def get_by_iban(self, iban: str) -> Account | None:
        row = self._session.scalar(select(models.Account).where(models.Account.iban == iban))
        return _account(row) if row else None

    def list(self) -> list[Account]:
        rows = self._session.scalars(select(models.Account).order_by(models.Account.id))
        return [_account(row) for row in rows]

    def add(self, new: NewAccount) -> Account:
        row = models.Account(
            name=new.name,
            bank=new.bank,
            iban=new.iban,
            currency=new.currency,
            account_type=new.account_type,
            parser_format=new.parser_format,
        )
        self._session.add(row)
        self._session.flush()
        return _account(row)

    def update(self, account_id: int, changes: Mapping[str, str]) -> Account:
        row = self._session.get(models.Account, account_id)
        if row is None:
            raise AccountNotFoundError(f"account {account_id} not found")
        for field, value in changes.items():
            setattr(row, field, value)
        try:
            self._session.flush()
        except IntegrityError as exc:
            raise DuplicateIbanError("another account already uses this IBAN") from exc
        return _account(row)


class SqlImportRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def hash_exists(self, file_hash: str) -> bool:
        stmt = select(models.Import.id).where(models.Import.file_hash == file_hash)
        return self._session.scalar(stmt) is not None

    def add(self, account_id: int, file_name: str, file_hash: str) -> int:
        row = models.Import(
            account_id=account_id, file_name=file_name, file_hash=file_hash, status="running"
        )
        self._session.add(row)
        self._session.flush()
        return row.id

    def complete(self, import_id: int, counts: ImportCounts) -> ImportRecord:
        self._session.execute(
            update(models.Import)
            .where(models.Import.id == import_id)
            .values(
                status="completed",
                new_count=counts.new,
                duplicate_count=counts.duplicates,
                rule_matched_count=counts.rule_matched,
                llm_matched_count=counts.llm_matched,
                uncategorized_count=counts.uncategorized,
            )
        )
        row = self._session.get_one(models.Import, import_id)
        self._session.refresh(row)
        return _import_record(row)

    def list(self) -> list[ImportRecord]:
        rows = self._session.scalars(
            select(models.Import).order_by(models.Import.created_at.desc(), models.Import.id.desc())
        )
        return [_import_record(row) for row in rows]

    def release_for_manual(self, import_id: int, previous_source: str | None) -> None:
        column = {
            None: models.Import.uncategorized_count,
            "rule": models.Import.rule_matched_count,
            "llm": models.Import.llm_matched_count,
        }.get(previous_source)
        if column is None:  # manual to manual: already outside every count
            return
        self._session.execute(
            update(models.Import)
            .where(models.Import.id == import_id)
            .values({column.key: column - 1})
        )

    def move_to_llm_matched(self, counts_by_import: Mapping[int, int]) -> None:
        for import_id, count in counts_by_import.items():
            self._session.execute(
                update(models.Import)
                .where(models.Import.id == import_id)
                .values(
                    llm_matched_count=models.Import.llm_matched_count + count,
                    uncategorized_count=models.Import.uncategorized_count - count,
                )
            )


class SqlTransactionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def existing_fingerprints(self, account_id: int, fingerprints: Sequence[str]) -> set[str]:
        if not fingerprints:
            return set()
        stmt = select(models.Transaction.fingerprint).where(
            models.Transaction.account_id == account_id,
            models.Transaction.fingerprint.in_(fingerprints),
        )
        return set(self._session.scalars(stmt))

    def add_many(
        self, account_id: int, import_id: int, rows: Sequence[PreparedTransaction]
    ) -> None:
        models_and_rows = [
            (
                models.Transaction(
                    account_id=account_id,
                    import_id=import_id,
                    booking_date=row.transaction.booking_date,
                    value_date=row.transaction.value_date,
                    amount=row.transaction.amount,
                    currency=row.transaction.currency,
                    counterparty_raw=row.transaction.counterparty,
                    counterparty_normalized=row.counterparty_normalized,
                    counterparty_iban=row.transaction.counterparty_iban,
                    purpose=row.transaction.purpose,
                    fingerprint=row.fingerprint,
                    raw_row=dict(row.transaction.raw),
                    category_slug=row.categorization.category_slug if row.categorization else None,
                    category_source="rule" if row.categorization else None,
                ),
                row,
            )
            for row in rows
        ]
        self._session.add_all(model for model, _ in models_and_rows)
        self._session.flush()  # assigns the transaction ids the events refer to
        self._session.add_all(
            models.CategorizationEvent(
                transaction_id=model.id,
                category_slug=row.categorization.category_slug,
                source="rule",
                applied=True,
                rule_id=row.categorization.rule_id,
                rules_hash=row.categorization.rules_hash,
            )
            for model, row in models_and_rows
            if row.categorization
        )
        self._session.flush()

    def list_uncategorized(self, import_id: int | None = None) -> list[Candidate]:
        stmt = (
            select(models.Transaction, models.Account.iban)
            .join(models.Account, models.Account.id == models.Transaction.account_id)
            .where(models.Transaction.category_source.is_(None))
            .order_by(models.Transaction.id)
        )
        if import_id is not None:
            stmt = stmt.where(models.Transaction.import_id == import_id)
        return [_candidate(row, iban) for row, iban in self._session.execute(stmt)]

    def apply_llm_outcomes(self, outcomes: Sequence[LLMOutcome], model_name: str) -> dict[int, int]:
        applied_by_import: Counter[int] = Counter()
        for outcome in outcomes:
            suggestion = outcome.suggestion
            if suggestion is None:
                continue
            assigned = False
            if outcome.applied:
                # Guarded: a transaction categorized in the meantime (e.g. manually) is kept.
                import_id = self._session.scalar(
                    update(models.Transaction)
                    .where(
                        models.Transaction.id == outcome.transaction_id,
                        models.Transaction.category_source.is_(None),
                    )
                    .values(category_slug=suggestion.category_slug, category_source="llm")
                    .returning(models.Transaction.import_id)
                )
                if import_id is not None:
                    applied_by_import[import_id] += 1
                    assigned = True
            self._session.add(
                models.CategorizationEvent(
                    transaction_id=outcome.transaction_id,
                    category_slug=suggestion.category_slug,
                    source="llm",
                    applied=assigned,
                    model_name=model_name,
                    confidence=Decimal(str(round(suggestion.confidence, 3))),
                )
            )
        self._session.flush()
        return dict(applied_by_import)

    def list_uncategorized_page(self, limit: int, offset: int) -> UncategorizedPage:
        uncategorized = models.Transaction.category_source.is_(None)
        total = self._session.scalar(select(func.count()).where(uncategorized)) or 0
        rows = self._session.scalars(
            select(models.Transaction)
            .where(uncategorized)
            .order_by(models.Transaction.booking_date.desc(), models.Transaction.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        events = self._session.scalars(
            select(models.CategorizationEvent)
            .where(
                models.CategorizationEvent.transaction_id.in_([r.id for r in rows]),
                models.CategorizationEvent.source == "llm",
                models.CategorizationEvent.applied.is_(False),
            )
            .order_by(
                models.CategorizationEvent.created_at.desc(), models.CategorizationEvent.id.desc()
            )
        ).all()
        suggestions: dict[int, list[Suggestion]] = {}
        for event in events:
            suggestions.setdefault(event.transaction_id, []).append(
                Suggestion(
                    category_slug=event.category_slug,
                    confidence=float(event.confidence) if event.confidence is not None else None,
                    model_name=event.model_name,
                    created_at=event.created_at,
                )
            )
        return UncategorizedPage(
            total=total,
            items=tuple(
                UncategorizedTransaction(
                    transaction_id=row.id,
                    account_id=row.account_id,
                    booking_date=row.booking_date,
                    amount=row.amount,
                    currency=row.currency,
                    counterparty=row.counterparty_raw,
                    purpose=row.purpose,
                    suggestions=tuple(suggestions.get(row.id, ())),
                )
                for row in rows
            ),
        )

    def search(self, filters: TransactionFilter, limit: int, offset: int) -> ExplorerPage:
        stmt = select(models.Transaction)
        if filters.account_id is not None:
            stmt = stmt.where(models.Transaction.account_id == filters.account_id)
        if filters.date_from is not None:
            stmt = stmt.where(models.Transaction.booking_date >= filters.date_from)
        if filters.date_to is not None:
            stmt = stmt.where(models.Transaction.booking_date <= filters.date_to)
        if filters.category is not None:
            children = select(models.Category.slug).where(
                models.Category.parent_slug == filters.category
            )
            stmt = stmt.where(
                or_(
                    models.Transaction.category_slug == filters.category,
                    models.Transaction.category_slug.in_(children),
                )
            )
        if filters.text:
            stmt = stmt.where(
                or_(
                    models.Transaction.counterparty_raw.icontains(filters.text, autoescape=True),
                    models.Transaction.purpose.icontains(filters.text, autoescape=True),
                )
            )
        if filters.source == "none":
            stmt = stmt.where(models.Transaction.category_source.is_(None))
        elif filters.source is not None:
            stmt = stmt.where(models.Transaction.category_source == filters.source)

        total = self._session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self._session.scalars(
            stmt.order_by(models.Transaction.booking_date.desc(), models.Transaction.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return ExplorerPage(
            total=total,
            items=tuple(
                ExplorerTransaction(
                    transaction_id=row.id,
                    account_id=row.account_id,
                    booking_date=row.booking_date,
                    amount=row.amount,
                    currency=row.currency,
                    counterparty=row.counterparty_raw,
                    purpose=row.purpose,
                    category=row.category_slug,
                    category_source=row.category_source,
                )
                for row in rows
            ),
        )

    def set_manual_category(self, transaction_id: int, category_slug: str) -> ManualOverride:
        row = self._session.scalar(
            select(models.Transaction)
            .where(models.Transaction.id == transaction_id)
            .with_for_update()
        )
        if row is None:
            raise TransactionNotFoundError(f"transaction {transaction_id} not found")
        previous_source = row.category_source
        row.category_slug = category_slug
        row.category_source = "manual"
        self._session.add(
            models.CategorizationEvent(
                transaction_id=transaction_id,
                category_slug=category_slug,
                source="manual",
                applied=True,
            )
        )
        self._session.flush()
        return ManualOverride(transaction_id, row.import_id, previous_source)

    def list_for_recategorization(self) -> list[Candidate]:
        stmt = (
            select(models.Transaction, models.Account.iban)
            .join(models.Account, models.Account.id == models.Transaction.account_id)
            .where(models.Transaction.category_source.is_distinct_from("manual"))
            .order_by(models.Transaction.id)
        )
        return [_candidate(row, iban) for row, iban in self._session.execute(stmt)]

    def apply_rule_changes(self, changes: Sequence[Change], rules_hash: str) -> None:
        if not changes:
            return
        self._session.execute(
            update(models.Transaction),
            [
                {
                    "id": change.transaction_id,
                    "category_slug": change.new_category_slug,
                    "category_source": "rule" if change.new_category_slug else None,
                }
                for change in changes
            ],
        )
        self._session.add_all(
            models.CategorizationEvent(
                transaction_id=change.transaction_id,
                category_slug=change.new_category_slug,
                source="rule",
                applied=True,
                rule_id=change.rule_id,
                rules_hash=rules_hash,
            )
            for change in changes
        )
        self._session.flush()


class SqlCategoryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def is_assignable(self, slug: str) -> bool:
        stmt = select(models.Category.slug).where(
            models.Category.slug == slug, models.Category.parent_slug.is_not(None)
        )
        return self._session.scalar(stmt) is not None

    def upsert_all(self, categories: Sequence[CategoryDef]) -> None:
        # Parents first, so the foreign key of every subcategory is satisfied.
        for level in (
            [c for c in categories if c.parent_slug is None],
            [c for c in categories if c.parent_slug is not None],
        ):
            if not level:
                continue
            stmt = insert(models.Category).values(
                [
                    {"slug": c.slug, "parent_slug": c.parent_slug, "name": c.name, "kind": c.kind}
                    for c in level
                ]
            )
            self._session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["slug"],
                    set_={
                        "parent_slug": stmt.excluded.parent_slug,
                        "name": stmt.excluded.name,
                        "kind": stmt.excluded.kind,
                    },
                )
            )


def _view_filters(month: int | None, account_id: int | None) -> tuple[str, dict[str, int]]:
    """WHERE fragments over the report views. Only constant SQL; values are bound."""
    sql = "year = :year"
    params: dict[str, int] = {}
    if month is not None:
        sql += " AND month = :month"
        params["month"] = month
    if account_id is not None:
        sql += " AND account_id = :account_id"
        params["account_id"] = account_id
    return sql, params


class SqlReportRepository:
    """Reads the report views created by the migrations (CONTRACT §11.3)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def category_spending(
        self, year: int, month: int | None, account_id: int | None
    ) -> list[CategorySpendingRow]:
        where, params = _view_filters(month, account_id)
        result = self._session.execute(
            text(
                "SELECT currency, top_slug, top_name, sub_slug, sub_name, uncategorized, "
                "SUM(spent) AS spent, SUM(transaction_count)::int AS transaction_count "
                f"FROM v_monthly_category_spending WHERE {where} "
                "GROUP BY currency, top_slug, top_name, sub_slug, sub_name, uncategorized"
            ),
            {"year": year, **params},
        )
        return [CategorySpendingRow(**row._mapping) for row in result]

    def income_expenses(self, year: int, account_id: int | None) -> list[IncomeExpensesRow]:
        where, params = _view_filters(None, account_id)
        result = self._session.execute(
            text(
                "SELECT currency, month, SUM(income) AS income, SUM(expenses) AS expenses, "
                "SUM(uncategorized_count)::int AS uncategorized_count "
                f"FROM v_monthly_income_expenses WHERE {where} GROUP BY currency, month"
            ),
            {"year": year, **params},
        )
        return [IncomeExpensesRow(**row._mapping) for row in result]

    def top_merchants(
        self, year: int, month: int | None, account_id: int | None, limit: int
    ) -> list[MerchantRow]:
        where, params = _view_filters(month, account_id)
        result = self._session.execute(
            text(
                "SELECT currency, counterparty_normalized AS merchant, SUM(spent) AS spent, "
                "SUM(transaction_count)::int AS transaction_count "
                f"FROM v_merchant_spending WHERE {where} "
                "GROUP BY currency, counterparty_normalized "
                "ORDER BY SUM(spent) DESC, counterparty_normalized LIMIT :limit"
            ),
            {"year": year, "limit": limit, **params},
        )
        return [MerchantRow(**row._mapping) for row in result]
