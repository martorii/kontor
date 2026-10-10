from datetime import date, datetime, time
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, JsonValue, StringConstraints

from kontor.domain.account import Account
from kontor.domain.agent import AgentAnswer, ChartSpec
from kontor.domain.imports import ImportRecord, ImportResult
from kontor.domain.llm import LLMProgress, LLMRunResult
from kontor.domain.recategorization import RerunResult
from kontor.domain.review import UncategorizedPage
from kontor.domain.rules import CategoryDef


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    bank: str
    iban: str
    currency: str
    account_type: str
    parser_format: str

    @classmethod
    def from_domain(cls, account: Account) -> "AccountResponse":
        return cls.model_validate(account)


class AccountUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    bank: str | None = None
    iban: str | None = None
    currency: str | None = None
    account_type: str | None = None
    parser_format: str | None = None


class ImportResponse(BaseModel):
    id: int
    account_id: int
    account_created: bool
    file_name: str
    status: str
    new_count: int
    duplicate_count: int
    rule_matched_count: int
    llm_matched_count: int
    uncategorized_count: int

    @classmethod
    def from_domain(cls, result: ImportResult) -> "ImportResponse":
        record = result.record
        return cls(
            id=record.id,
            account_id=record.account_id,
            account_created=result.account_created,
            file_name=record.file_name,
            status=record.status,
            new_count=record.counts.new,
            duplicate_count=record.counts.duplicates,
            rule_matched_count=record.counts.rule_matched,
            llm_matched_count=record.counts.llm_matched,
            uncategorized_count=record.counts.uncategorized,
        )


class ImportRecordResponse(BaseModel):
    id: int
    account_id: int
    file_name: str
    status: str
    created_at: datetime
    new_count: int
    duplicate_count: int
    rule_matched_count: int
    llm_matched_count: int
    uncategorized_count: int

    @classmethod
    def from_domain(cls, record: ImportRecord) -> "ImportRecordResponse":
        return cls(
            id=record.id,
            account_id=record.account_id,
            file_name=record.file_name,
            status=record.status,
            created_at=record.created_at,
            new_count=record.counts.new,
            duplicate_count=record.counts.duplicates,
            rule_matched_count=record.counts.rule_matched,
            llm_matched_count=record.counts.llm_matched,
            uncategorized_count=record.counts.uncategorized,
        )


class ChangeResponse(BaseModel):
    transaction_id: int
    old_category: str | None
    old_source: str | None
    new_category: str | None
    rule_id: str | None


class RerunResponse(BaseModel):
    rules_hash: str
    dry_run: bool
    evaluated: int
    changed: int
    unchanged: int
    changes: list[ChangeResponse]

    @classmethod
    def from_domain(cls, result: RerunResult) -> "RerunResponse":
        return cls(
            rules_hash=result.rules_hash,
            dry_run=result.dry_run,
            evaluated=result.evaluated,
            changed=len(result.changes),
            unchanged=result.evaluated - len(result.changes),
            changes=[
                ChangeResponse(
                    transaction_id=c.transaction_id,
                    old_category=c.old_category_slug,
                    old_source=c.old_category_source,
                    new_category=c.new_category_slug,
                    rule_id=c.rule_id,
                )
                for c in result.changes
            ],
        )


class LLMOutcomeResponse(BaseModel):
    transaction_id: int
    category: str | None
    confidence: float | None
    applied: bool
    error: str | None


class LLMProgressResponse(BaseModel):
    running: bool
    processed: int
    total: int
    import_id: int | None

    @classmethod
    def from_domain(cls, progress: LLMProgress) -> "LLMProgressResponse":
        return cls(
            running=progress.running,
            processed=progress.processed,
            total=progress.total,
            import_id=progress.import_id,
        )


class LLMRunResponse(BaseModel):
    dry_run: bool
    skipped: bool
    interrupted: bool
    evaluated: int
    applied: int
    suggested: int
    failed: int
    outcomes: list[LLMOutcomeResponse]

    @classmethod
    def from_domain(cls, result: LLMRunResult) -> "LLMRunResponse":
        return cls(
            dry_run=result.dry_run,
            skipped=result.skipped,
            interrupted=result.interrupted,
            evaluated=result.evaluated,
            applied=result.applied,
            suggested=result.suggested,
            failed=result.failed,
            outcomes=[
                LLMOutcomeResponse(
                    transaction_id=o.transaction_id,
                    category=o.suggestion.category_slug if o.suggestion else None,
                    confidence=o.suggestion.confidence if o.suggestion else None,
                    applied=o.applied,
                    error=o.error,
                )
                for o in result.outcomes
            ],
        )


class SuggestionResponse(BaseModel):
    category: str | None
    confidence: float | None
    model: str | None
    created_at: datetime


class UncategorizedTransactionResponse(BaseModel):
    id: int
    account_id: int
    booking_date: date
    amount: Decimal
    currency: str
    counterparty: str
    purpose: str
    suggestions: list[SuggestionResponse]  # newest first


class UncategorizedPageResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[UncategorizedTransactionResponse]

    @classmethod
    def from_domain(
        cls, page: UncategorizedPage, limit: int, offset: int
    ) -> "UncategorizedPageResponse":
        return cls(
            total=page.total,
            limit=limit,
            offset=offset,
            items=[
                UncategorizedTransactionResponse(
                    id=t.transaction_id,
                    account_id=t.account_id,
                    booking_date=t.booking_date,
                    amount=t.amount,
                    currency=t.currency,
                    counterparty=t.counterparty,
                    purpose=t.purpose,
                    suggestions=[
                        SuggestionResponse(
                            category=s.category_slug,
                            confidence=s.confidence,
                            model=s.model_name,
                            created_at=s.created_at,
                        )
                        for s in t.suggestions
                    ],
                )
                for t in page.items
            ],
        )


class CategoryResponse(BaseModel):
    slug: str
    name: str
    parent_slug: str | None

    @classmethod
    def from_domain(cls, category: CategoryDef) -> "CategoryResponse":
        return cls(slug=category.slug, name=category.name, parent_slug=category.parent_slug)


class CategorySet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str


class CategorySetResponse(BaseModel):
    transaction_id: int
    category: str
    source: str


Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: Question
    conversation_id: str | None = None


class ChartResponse(BaseModel):
    type: Literal["bar", "line", "none"]
    x: str | None
    y: str | None

    @classmethod
    def from_domain(cls, chart: ChartSpec) -> "ChartResponse":
        return cls(type=chart.type, x=chart.x, y=chart.y)


class AskResponse(BaseModel):
    """An agent answer (CONTRACT §16.6). Money comes back as strings, never as floats."""

    conversation_id: str
    status: Literal["answered", "gave_up"]
    answer: str
    sql: str | None
    columns: list[str]
    rows: list[list[JsonValue]]
    truncated: bool
    chart: ChartResponse
    attempts: int
    last_error: str | None

    @classmethod
    def from_domain(cls, conversation_id: str, answer: AgentAnswer) -> "AskResponse":
        result = answer.result
        return cls(
            conversation_id=conversation_id,
            status=answer.status,
            answer=answer.answer,
            sql=answer.sql,
            columns=list(result.columns) if result else [],
            rows=[[to_json_value(v) for v in row] for row in result.rows] if result else [],
            truncated=result.truncated if result else False,
            chart=ChartResponse.from_domain(answer.chart),
            attempts=answer.attempts,
            last_error=answer.last_error,
        )


def to_json_value(value: object) -> JsonValue:
    """One agent result cell as JSON. Decimal becomes a string so no precision is lost."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date | datetime | time):
        return value.isoformat()
    if isinstance(value, dict | list):
        # JSONB columns: psycopg already decoded them into JSON-compatible values.
        return value
    return str(value)
