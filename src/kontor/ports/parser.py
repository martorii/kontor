from dataclasses import dataclass
from typing import Protocol

from kontor.domain.transaction import Transaction


@dataclass(frozen=True, slots=True)
class ParsedStatement:
    """The result of parsing one bank export."""

    iban: str
    transactions: tuple[Transaction, ...]


class BankParser(Protocol):
    """One bank format. Adding a bank means adding one parser."""

    format_name: str
    bank: str
    account_type: str

    def detect(self, content: bytes) -> bool:
        """Whether this parser recognizes the file, judged from its header only."""
        ...

    def parse(self, content: bytes) -> ParsedStatement:
        """Map the file to canonical transactions. Raises MalformedFileError on bad content."""
        ...
