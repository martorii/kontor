import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from kontor.domain.errors import MalformedFileError
from kontor.domain.transaction import Transaction
from kontor.ports.parser import ParsedStatement

_IBAN = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$")
_FIRST_COLUMN = "Buchungsdatum"
_REQUIRED_COLUMNS = (
    "Buchungsdatum",
    "Wertstellung",
    "Status",
    "Zahlungspflichtige*r",
    "Zahlungsempfänger*in",
    "Verwendungszweck",
    "IBAN",
    "Betrag (€)",
)
_BOOKED = "Gebucht"


def _rows(content: bytes) -> list[list[str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise MalformedFileError("file is not valid UTF-8") from exc
    return list(csv.reader(io.StringIO(text), delimiter=";"))


def _header_index(rows: list[list[str]]) -> int | None:
    for index, row in enumerate(rows):
        if row and row[0] == _FIRST_COLUMN:
            return index
    return None


def _parse_date(value: str, column: str) -> date:
    try:
        return datetime.strptime(value, "%d.%m.%y").date()
    except ValueError as exc:
        raise MalformedFileError(f"invalid date in {column}: {value!r}") from exc


def _parse_amount(value: str) -> Decimal:
    cleaned = value.replace("€", "").replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise MalformedFileError(f"invalid amount: {value!r}") from exc


class DkbParser:
    """DKB checking account (Girokonto) CSV export."""

    format_name = "dkb"
    bank = "DKB"
    account_type = "checking"

    def detect(self, content: bytes) -> bool:
        try:
            rows = _rows(content)
        except MalformedFileError:
            return False
        index = _header_index(rows)
        return index is not None and all(c in rows[index] for c in _REQUIRED_COLUMNS)

    def parse(self, content: bytes) -> ParsedStatement:
        rows = _rows(content)
        header_index = _header_index(rows)
        if header_index is None:
            raise MalformedFileError("header row not found")
        header = rows[header_index]
        missing = [c for c in _REQUIRED_COLUMNS if c not in header]
        if missing:
            raise MalformedFileError(f"missing columns: {', '.join(missing)}")

        iban = self._iban(rows[:header_index])
        transactions: list[Transaction] = []
        for line, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
            if not any(cell.strip() for cell in row):
                continue
            if len(row) != len(header):
                raise MalformedFileError(f"line {line}: expected {len(header)} columns")
            record = dict(zip(header, row, strict=True))
            if record["Status"] != _BOOKED:
                continue  # pending rows change later and would break idempotency
            transactions.append(self._transaction(record, line))
        return ParsedStatement(iban=iban, transactions=tuple(transactions))

    @staticmethod
    def _iban(preamble: list[list[str]]) -> str:
        for row in preamble:
            if len(row) >= 2 and row[0] == "Girokonto":
                iban = row[1].replace(" ", "")
                if _IBAN.match(iban):
                    return iban
                raise MalformedFileError(f"invalid IBAN in preamble: {row[1]!r}")
        raise MalformedFileError("account IBAN not found in preamble")

    @staticmethod
    def _transaction(record: dict[str, str], line: int) -> Transaction:
        try:
            amount = _parse_amount(record["Betrag (€)"])
            booking_date = _parse_date(record["Buchungsdatum"], "Buchungsdatum")
            value_date = _parse_date(record["Wertstellung"], "Wertstellung")
        except MalformedFileError as exc:
            raise MalformedFileError(f"line {line}: {exc}") from exc
        # The account holder is the other side of the booking, so the counterparty is the payee
        # of an outflow and the payer of an inflow.
        counterparty = (
            record["Zahlungsempfänger*in"] if amount < 0 else record["Zahlungspflichtige*r"]
        )
        return Transaction(
            booking_date=booking_date,
            value_date=value_date,
            amount=amount,
            currency="EUR",
            counterparty=counterparty,
            counterparty_iban=record["IBAN"] or None,
            purpose=record["Verwendungszweck"],
            raw=record,
        )
