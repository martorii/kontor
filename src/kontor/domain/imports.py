from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ImportCounts:
    new: int
    duplicates: int
    rule_matched: int = 0
    llm_matched: int = 0
    uncategorized: int = 0


@dataclass(frozen=True, slots=True)
class ImportRecord:
    id: int
    account_id: int
    file_name: str
    file_hash: str
    status: str
    created_at: datetime
    counts: ImportCounts


@dataclass(frozen=True, slots=True)
class ImportResult:
    record: ImportRecord
    account_created: bool
