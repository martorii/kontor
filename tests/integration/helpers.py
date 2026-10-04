from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

FIXTURES = Path(__file__).parents[1] / "fixtures"
IBAN = "DE89370400440532013000"
HEADER = (
    '"Buchungsdatum";"Wertstellung";"Status";"Zahlungspflichtige*r";"Zahlungsempfänger*in";'
    '"Verwendungszweck";"Umsatztyp";"IBAN";"Betrag (€)";"Gläubiger-ID";"Mandatsreferenz";'
    '"Kundenreferenz"'
)


def row(day: str, payee: str, amount: str, status: str = "Gebucht") -> str:
    return (
        f'"{day}";"{day}";"{status}";"Erika Musterfrau";"{payee}";"Kartenzahlung";"Ausgang";'
        f'"";"{amount}";"";"";""'
    )


def dkb_file(rows: list[str], iban: str = IBAN) -> bytes:
    preamble = f'"Girokonto";"{iban}"\n"Zeitraum:";"01.03.2026 - 31.03.2026"\n""\n'
    return (preamble + HEADER + "\n" + "\n".join(rows) + "\n").encode()


def upload(client: TestClient, content: bytes, name: str = "export.csv"):  # type: ignore[no-untyped-def]
    return client.post("/imports", files={"file": (name, content, "text/csv")})


def count(engine: Engine, table: str) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())
