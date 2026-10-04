import re

_DATE = re.compile(r"\b\d{1,2}\.\d{1,2}\.(?:\d{4}|\d{2})\b|\b\d{4}-\d{2}-\d{2}\b")
# Store, terminal and card numbers: a marker word followed by a number, or a bare "#123".
_MARKED_NUMBER = re.compile(
    r"\b(?:FILIALE|FIL|STORE|MARKT|NR|NUMMER|TERMINAL|TERM|KARTE|KARTENNR|KARTEN-NR|"
    r"TRACE|BELEG)\b\.?\s*:?\s*#?\d+|#\d+"
)
_LONG_DIGITS = re.compile(r"\b\d{5,}\b")
_BOILERPLATE = re.compile(
    r"\b(?:SEPA[- ]?(?:LASTSCHRIFT|UEBERWEISUNG|ÜBERWEISUNG|BASISLASTSCHRIFT)?|"
    r"KARTENZAHLUNG|KARTENUMSATZ|LASTSCHRIFT|GIROPAY|ONLINE[- ]?(?:BANKING|UEBERWEISUNG)|"
    r"EREF|MREF|CRED|SVWZ|ENTGELTABSCHLUSS)\b\+?:?"
)
_SEPARATORS = re.compile(r"[^\w&]+")


def normalize_text(text: str) -> str:
    """Normalize free text for matching: uppercase, store numbers, dates and boilerplate removed."""
    result = text.upper()
    for pattern in (_DATE, _MARKED_NUMBER, _BOILERPLATE, _LONG_DIGITS):
        result = pattern.sub(" ", result)
    return _SEPARATORS.sub(" ", result).strip()


def normalize_counterparty(counterparty: str) -> str:
    return normalize_text(counterparty)


def normalize_purpose(purpose: str) -> str:
    return normalize_text(purpose)
