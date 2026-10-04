from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NewAccount:
    name: str
    bank: str
    iban: str
    currency: str
    account_type: str
    parser_format: str


@dataclass(frozen=True, slots=True)
class Account:
    id: int
    name: str
    bank: str
    iban: str
    currency: str
    account_type: str
    parser_format: str
