import pytest

from kontor.domain.normalization import normalize_counterparty, normalize_purpose


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Rewe Markt GmbH", "REWE MARKT GMBH"),
        ("REWE SAGT DANKE FILIALE 1234", "REWE SAGT DANKE"),
        ("Edeka Nr. 4711", "EDEKA"),
        ("Bäckerei Müller #55", "BÄCKEREI MÜLLER"),
        ("KARTENZAHLUNG Lidl 12.03.2026 TERMINAL 998", "LIDL"),
        ("SEPA-LASTSCHRIFT Stadtwerke 2026-03-12", "STADTWERKE"),
        ("Netflix   1234567890", "NETFLIX"),
        ("  amazon.de  ", "AMAZON DE"),
    ],
)
def test_normalize_counterparty(raw: str, expected: str) -> None:
    assert normalize_counterparty(raw) == expected


def test_normalization_is_idempotent() -> None:
    once = normalize_counterparty("KARTENZAHLUNG Rewe FILIALE 12 am 01.02.25")
    assert normalize_counterparty(once) == once


def test_purpose_strips_dates_and_boilerplate() -> None:
    assert normalize_purpose("SVWZ+ Miete März 01.03.2026 EREF: 12345678") == "MIETE MÄRZ"


def test_empty_text() -> None:
    assert normalize_counterparty("") == ""
