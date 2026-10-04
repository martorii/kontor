from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from kontor.adapters.parsers.dkb import DkbParser
from kontor.adapters.parsers.registry import default_registry
from kontor.domain.errors import MalformedFileError, UnknownFormatError

FIXTURES = Path(__file__).parents[2] / "fixtures"


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_detects_dkb_file() -> None:
    assert DkbParser().detect(fixture("dkb_girokonto.csv"))


def test_does_not_detect_other_file() -> None:
    assert not DkbParser().detect(fixture("unknown_format.csv"))
    assert not DkbParser().detect(b"\xff\xfe\x00")


def test_registry_detects_dkb() -> None:
    assert default_registry().detect(fixture("dkb_girokonto.csv")).format_name == "dkb"


def test_registry_unknown_format() -> None:
    with pytest.raises(UnknownFormatError):
        default_registry().detect(fixture("unknown_format.csv"))
    with pytest.raises(UnknownFormatError):
        default_registry().get("nope")


def test_extracts_iban() -> None:
    assert DkbParser().parse(fixture("dkb_girokonto.csv")).iban == "DE89370400440532013000"


def test_maps_rows_field_by_field() -> None:
    statement = DkbParser().parse(fixture("dkb_girokonto.csv"))
    # The pending row is skipped.
    assert len(statement.transactions) == 3

    outflow, short_decimal, inflow = statement.transactions
    assert outflow.booking_date == date(2026, 3, 12)
    assert outflow.value_date == date(2026, 3, 12)
    assert outflow.amount == Decimal("-15.15")
    assert outflow.currency == "EUR"
    assert outflow.counterparty == "Beispiel Baeckerei"
    assert outflow.counterparty_iban == "DE02120300000000202051"
    assert outflow.purpose == "VISA Debitkartenumsatz vom 10.03.2026"
    assert outflow.raw["Kundenreferenz"] == "0000000000000001"

    assert short_decimal.amount == Decimal("-9.5")

    # For an inflow the counterparty is the payer.
    assert inflow.amount == Decimal("2450.00")
    assert inflow.counterparty == "Beispiel Arbeitgeber GmbH"


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b'"Girokonto";"DE89370400440532013000"\n',
        b'"Girokonto";"NOT-AN-IBAN"\n"Buchungsdatum";"Wertstellung";"Status";"Zahlungspflichtige*r";'
        b'"Zahlungsempf\xc3\xa4nger*in";"Verwendungszweck";"IBAN";"Betrag (\xe2\x82\xac)"\n',
    ],
)
def test_malformed_files(content: bytes) -> None:
    with pytest.raises(MalformedFileError):
        DkbParser().parse(content)


def _with_row(row: str) -> bytes:
    text = fixture("dkb_girokonto.csv").decode().rstrip("\n")
    return f"{text}\n{row}\n".encode()


def test_bad_amount_reports_line() -> None:
    row = '"15.03.26";"15.03.26";"Gebucht";"A";"B";"x";"Ausgang";"";"abc";"";"";""'
    with pytest.raises(MalformedFileError, match="line 10"):
        DkbParser().parse(_with_row(row))


def test_bad_date_and_column_count() -> None:
    with pytest.raises(MalformedFileError, match="invalid date"):
        DkbParser().parse(
            _with_row('"99.99.26";"15.03.26";"Gebucht";"A";"B";"x";"";"";"1,00";"";"";""')
        )
    with pytest.raises(MalformedFileError, match="columns"):
        DkbParser().parse(_with_row('"15.03.26";"15.03.26"'))


def test_non_utf8_is_malformed() -> None:
    with pytest.raises(MalformedFileError, match="UTF-8"):
        DkbParser().parse(b"\xff\xfe\x00")
