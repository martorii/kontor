from pydantic import BaseModel, ConfigDict

from kontor.domain.account import Account
from kontor.domain.imports import ImportResult
from kontor.domain.llm import LLMRunResult
from kontor.domain.recategorization import RerunResult


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
