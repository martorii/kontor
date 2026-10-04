from fastapi.testclient import TestClient
from helpers import FIXTURES, IBAN, count, dkb_file, row, upload
from sqlalchemy import Engine


def test_first_import(client: TestClient, engine: Engine) -> None:
    response = upload(client, (FIXTURES / "dkb_girokonto.csv").read_bytes(), "dkb.csv")

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["file_name"] == "dkb.csv"
    assert body["new_count"] == 3  # the pending row is skipped by the parser
    assert body["duplicate_count"] == 0
    assert body["rule_matched_count"] == 1  # the salary row matches an example rule
    assert body["uncategorized_count"] == 2
    assert count(engine, "transactions") == 3
    assert count(engine, "imports") == 1


def test_same_file_is_rejected(client: TestClient, engine: Engine) -> None:
    content = dkb_file([row("12.03.26", "Shop A", "-5,00")])
    assert upload(client, content).status_code == 201

    response = upload(client, content)

    assert response.status_code == 409
    assert response.json()["error"] == "DuplicateFileError"
    assert count(engine, "imports") == 1
    assert count(engine, "transactions") == 1


def test_overlapping_file_inserts_only_new_rows(client: TestClient, engine: Engine) -> None:
    first = dkb_file([row("10.03.26", "Shop A", "-5,00"), row("12.03.26", "Shop B", "-7,50")])
    second = dkb_file([row("12.03.26", "Shop B", "-7,50"), row("14.03.26", "Shop C", "-3,00")])
    upload(client, first)

    response = upload(client, second)

    assert response.status_code == 201
    assert response.json()["new_count"] == 1
    assert response.json()["duplicate_count"] == 1
    assert count(engine, "transactions") == 3


def test_identical_rows_in_one_file_are_kept_and_not_reimported(
    client: TestClient, engine: Engine
) -> None:
    coffee = row("12.03.26", "Baeckerei", "-3,50")
    assert upload(client, dkb_file([coffee, coffee])).json()["new_count"] == 2

    again = upload(client, dkb_file([coffee, coffee, row("13.03.26", "Shop", "-1,00")]))

    assert again.json()["new_count"] == 1
    assert again.json()["duplicate_count"] == 2
    assert count(engine, "transactions") == 3


def test_unknown_iban_creates_account_and_known_iban_reuses_it(
    client: TestClient, engine: Engine
) -> None:
    first = upload(client, dkb_file([row("10.03.26", "Shop A", "-5,00")]))
    second = upload(client, dkb_file([row("11.03.26", "Shop B", "-6,00")]))

    assert first.json()["account_created"] is True
    assert second.json()["account_created"] is False
    assert first.json()["account_id"] == second.json()["account_id"]
    assert count(engine, "accounts") == 1

    account = client.get(f"/accounts/{first.json()['account_id']}").json()
    assert account["iban"] == IBAN
    assert account["bank"] == "DKB"
    assert account["account_type"] == "checking"
    assert account["parser_format"] == "dkb"
    assert account["currency"] == "EUR"


def test_parse_error_rolls_back_the_whole_file(client: TestClient, engine: Engine) -> None:
    content = dkb_file([row("10.03.26", "Shop A", "-5,00"), row("11.03.26", "Shop B", "oops")])

    response = upload(client, content)

    assert response.status_code == 422
    assert response.json()["error"] == "MalformedFileError"
    for table in ("accounts", "imports", "transactions"):
        assert count(engine, table) == 0
    # The corrected file can be uploaded afterwards.
    fixed = dkb_file([row("10.03.26", "Shop A", "-5,00"), row("11.03.26", "Shop B", "-1,00")])
    assert upload(client, fixed).status_code == 201


def test_unknown_format_is_rejected(client: TestClient, engine: Engine) -> None:
    response = upload(client, (FIXTURES / "unknown_format.csv").read_bytes())

    assert response.status_code == 422
    assert response.json()["error"] == "UnknownFormatError"
    assert count(engine, "imports") == 0


def test_accounts_list_get_and_patch(client: TestClient) -> None:
    account_id = upload(client, dkb_file([row("10.03.26", "Shop A", "-5,00")])).json()["account_id"]

    assert [a["id"] for a in client.get("/accounts").json()] == [account_id]

    patched = client.patch(f"/accounts/{account_id}", json={"name": "Daily", "account_type": "x"})
    assert patched.status_code == 200
    assert patched.json()["name"] == "Daily"
    assert patched.json()["account_type"] == "x"
    assert patched.json()["bank"] == "DKB"

    assert client.get("/accounts/999").status_code == 404
    assert client.patch("/accounts/999", json={"name": "x"}).status_code == 404
    assert client.patch(f"/accounts/{account_id}", json={"bogus": 1}).status_code == 422


def test_patching_to_an_existing_iban_conflicts(client: TestClient) -> None:
    first = upload(client, dkb_file([row("10.03.26", "A", "-1,00")])).json()["account_id"]
    other_iban = "DE02120300000000202051"
    upload(client, dkb_file([row("10.03.26", "A", "-1,00")], iban=other_iban))

    response = client.patch(f"/accounts/{first}", json={"iban": other_iban})

    assert response.status_code == 409
