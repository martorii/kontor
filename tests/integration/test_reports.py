from collections.abc import Callable
from decimal import Decimal

from fastapi.testclient import TestClient
from helpers import dkb_file, incoming_row, row, upload

RULES = """\
categories:
  - {slug: food, name: Food, kind: expense}
  - {slug: food.groceries, name: Groceries, parent: food}
  - {slug: food.restaurants, name: Restaurants, parent: food}
  - {slug: housing, name: Housing, kind: expense}
  - {slug: housing.rent, name: Rent, parent: housing}
  - {slug: salary, name: Salary, kind: income}
  - {slug: salary.main, name: Main job, parent: salary}
  - {slug: transfers, name: Transfers, kind: transfer}
  - {slug: transfers.own, name: Own accounts, parent: transfers}
  - {slug: savings, name: Savings, kind: savings}
  - {slug: savings.etf, name: ETF, parent: savings}
rules:
  - {id: rewe, category: food.groceries, field: counterparty, match: REWE}
  - {id: cafe, category: food.restaurants, field: counterparty, match: CAFE}
  - {id: rent, category: housing.rent, field: counterparty, match: LANDLORD}
  - {id: acme, category: salary.main, field: counterparty, match: ACME}
  - {id: own, category: transfers.own, field: counterparty, match: OWN ACCOUNT}
  - {id: etf, category: savings.etf, field: counterparty, match: BROKER}
"""

MakeClient = Callable[[str | None], TestClient]
OTHER_IBAN = "DE02120300000000202051"


def seed(client: TestClient) -> None:
    upload(
        client,
        dkb_file(
            [
                row("10.03.26", "REWE Markt", "-10,00"),
                row("11.03.26", "REWE Markt", "-20,50"),
                row("12.03.26", "CAFE Central", "-5,00"),
                row("01.03.26", "LANDLORD GmbH", "-500,00"),
                incoming_row("25.03.26", "ACME Corp", "3000,00"),
                row("26.03.26", "OWN ACCOUNT", "-200,00"),
                row("27.03.26", "BROKER AG", "-300,00"),
                row("28.03.26", "Mystery Shop", "-7,00"),
                incoming_row("29.03.26", "REWE Markt", "2,50"),  # a refund in an expense category
                row("14.04.26", "REWE Markt", "-40,00"),
                incoming_row("25.04.26", "ACME Corp", "3000,00"),
            ]
        ),
        "2026.csv",
    )
    upload(
        client,
        dkb_file(
            [
                row("10.03.25", "REWE Markt", "-25,00"),
                incoming_row("25.03.25", "ACME Corp", "2000,00"),
                row("01.03.25", "LANDLORD GmbH", "-400,00"),
            ]
        ),
        "2025.csv",
    )


def money(value: object) -> Decimal:
    return Decimal(str(value))


def test_monthly_overview_has_exact_totals_and_drill_down(make_client: MakeClient) -> None:
    client = make_client(RULES)
    seed(client)

    body = client.get("/reports/monthly", params={"year": 2026, "month": 3}).json()

    assert body["currency"] == "EUR"
    assert money(body["total"]) == Decimal("540.00")
    assert body["includes_uncategorized"] is True
    assert [(c["slug"], money(c["total"])) for c in body["categories"]] == [
        ("housing", Decimal("500.00")),
        ("food", Decimal("33.00")),
        ("uncategorized", Decimal("7.00")),
    ]
    food = body["categories"][1]
    assert [
        (s["slug"], money(s["total"]), s["transaction_count"]) for s in food["subcategories"]
    ] == [
        ("food.groceries", Decimal("28.00"), 3),  # 10.00 + 20.50 - 2.50 refund
        ("food.restaurants", Decimal("5.00"), 1),
    ]


def test_transfer_and_savings_are_not_spending(make_client: MakeClient) -> None:
    client = make_client(RULES)
    seed(client)

    monthly = client.get("/reports/monthly", params={"year": 2026, "month": 3}).json()
    slugs = {c["slug"] for c in monthly["categories"]}
    assert not slugs & {"transfers", "savings", "salary"}
    assert money(monthly["total"]) == Decimal("540.00")  # not 1040.00

    merchants = client.get("/reports/top-merchants", params={"year": 2026}).json()
    assert {m["merchant"] for m in merchants["merchants"]}.isdisjoint({"OWN ACCOUNT", "BROKER AG"})

    income = client.get("/reports/income-expenses", params={"year": 2026}).json()
    assert money(income["expenses"]) == Decimal("580.00")  # no transfer, no savings
    assert money(income["income"]) == Decimal("6000.00")


def test_year_comparison(make_client: MakeClient) -> None:
    client = make_client(RULES)
    seed(client)

    body = client.get("/reports/year", params={"year": 2026}).json()

    assert (body["year"], body["previous_year"]) == (2026, 2025)
    assert money(body["total"]) == Decimal("580.00")
    assert money(body["previous_total"]) == Decimal("425.00")
    assert money(body["change"]) == Decimal("155.00")
    by_slug = {c["slug"]: c for c in body["categories"]}
    assert money(by_slug["food"]["total"]) == Decimal("73.00")
    assert money(by_slug["food"]["previous_total"]) == Decimal("25.00")
    assert money(by_slug["food"]["change_ratio"]) == Decimal("1.9200")
    assert money(by_slug["housing"]["change_ratio"]) == Decimal("0.2500")
    assert by_slug["uncategorized"]["change_ratio"] is None  # nothing in 2025


def test_income_vs_expenses_by_month(make_client: MakeClient) -> None:
    client = make_client(RULES)
    seed(client)

    body = client.get("/reports/income-expenses", params={"year": 2026}).json()

    assert len(body["months"]) == 12
    march, april, may = body["months"][2], body["months"][3], body["months"][4]
    assert (money(march["income"]), money(march["expenses"]), money(march["net"])) == (
        Decimal("3000.00"),
        Decimal("540.00"),
        Decimal("2460.00"),
    )
    assert money(march["savings_rate"]) == Decimal("0.8200")
    assert money(april["expenses"]) == Decimal("40.00")
    assert money(april["savings_rate"]) == Decimal("0.9867")
    assert (money(may["income"]), may["savings_rate"]) == (Decimal(0), None)
    assert money(body["net"]) == Decimal("5420.00")
    assert money(body["savings_rate"]) == Decimal("0.9033")
    assert body["includes_uncategorized"] is True


def test_top_merchants(make_client: MakeClient) -> None:
    client = make_client(RULES)
    seed(client)

    top = client.get("/reports/top-merchants", params={"year": 2026, "limit": 2}).json()
    assert [(m["merchant"], money(m["total"])) for m in top["merchants"]] == [
        ("LANDLORD GMBH", Decimal("500.00")),
        ("REWE MARKT", Decimal("68.00")),
    ]
    assert top["merchants"][1]["transaction_count"] == 4

    april = client.get("/reports/top-merchants", params={"year": 2026, "month": 4}).json()
    assert [(m["merchant"], money(m["total"])) for m in april["merchants"]] == [
        ("REWE MARKT", Decimal("40.00"))
    ]


def test_reports_filter_by_account(make_client: MakeClient) -> None:
    client = make_client(RULES)
    seed(client)
    upload(
        client,
        dkb_file([row("10.03.26", "REWE Markt", "-1,00")], iban=OTHER_IBAN),
        "other.csv",
    )
    accounts = {a["iban"]: a["id"] for a in client.get("/accounts").json()}

    both = client.get("/reports/monthly", params={"year": 2026, "month": 3}).json()
    other = client.get(
        "/reports/monthly",
        params={"year": 2026, "month": 3, "account_id": accounts[OTHER_IBAN]},
    ).json()

    assert money(both["total"]) == Decimal("541.00")
    assert money(other["total"]) == Decimal("1.00")


def test_report_without_data_is_empty(make_client: MakeClient) -> None:
    client = make_client(RULES)

    body = client.get("/reports/monthly", params={"year": 2030, "month": 1}).json()

    assert body["currency"] is None
    assert money(body["total"]) == 0
    assert body["categories"] == []


def test_invalid_parameters_are_rejected(make_client: MakeClient) -> None:
    client = make_client(RULES)
    assert client.get("/reports/monthly", params={"year": 2026, "month": 13}).status_code == 422
    assert client.get("/reports/year").status_code == 422
