from pydantic import BaseModel, ConfigDict

from kontor.domain.account import Account
from kontor.domain.imports import ImportResult


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
