import json
from datetime import date

import httpx2 as httpx
import pytest

from api_client import ApiClient, ApiError, ApiTimeoutError, ApiUnreachableError


def client_with(handler: httpx.MockTransport) -> ApiClient:
    return ApiClient(base_url="http://api.test", transport=handler)


def test_upload_sends_the_file_as_multipart() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = request.content
        return httpx.Response(201, json={"id": 1, "file_name": "march.csv"})

    result = client_with(httpx.MockTransport(handler)).upload_import("march.csv", b"a;b")

    assert result["id"] == 1
    assert (seen["method"], seen["path"]) == ("POST", "/imports")
    assert b'filename="march.csv"' in seen["body"]  # type: ignore[operator]
    assert b"a;b" in seen["body"]  # type: ignore[operator]


def test_update_account_patches_only_the_given_fields() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, json={"id": 7, "name": "Main"})

    client_with(httpx.MockTransport(handler)).update_account(7, {"name": "Main"})

    assert (seen["method"], seen["path"], seen["json"]) == (
        "PATCH",
        "/accounts/7",
        {"name": "Main"},
    )


def test_list_endpoints() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"path": request.url.path}])

    client = client_with(httpx.MockTransport(handler))

    assert client.list_imports() == [{"path": "/imports"}]
    assert client.list_accounts() == [{"path": "/accounts"}]


def test_api_error_carries_the_readable_detail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409, json={"error": "DuplicateFileError", "detail": "already imported"}
        )

    with pytest.raises(ApiError) as caught:
        client_with(httpx.MockTransport(handler)).upload_import("x.csv", b"")

    assert caught.value.status_code == 409
    assert caught.value.detail == "already imported"


def test_error_without_a_detail_falls_back_to_the_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    with pytest.raises(ApiError) as caught:
        client_with(httpx.MockTransport(handler)).list_accounts()

    assert caught.value.detail == "HTTP 500"


def test_unreachable_api() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    with pytest.raises(ApiUnreachableError):
        client_with(httpx.MockTransport(handler)).list_accounts()


def test_report_sends_only_the_given_parameters() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = dict(request.url.params)
        return httpx.Response(200, json={"year": 2026})

    client = client_with(httpx.MockTransport(handler))
    client.top_merchants_report(date(2026, 1, 1), date(2026, 3, 31), [], 5)

    assert seen["path"] == "/reports/top-merchants"
    assert seen["query"] == {"date_from": "2026-01-01", "date_to": "2026-03-31", "limit": "5"}


def test_top_merchants_repeats_the_account_parameter() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["accounts"] = request.url.params.get_list("account_ids")
        return httpx.Response(200, json={})

    client = client_with(httpx.MockTransport(handler))
    client.top_merchants_report(date(2026, 1, 1), date(2026, 3, 31), [3, 4], 5)

    assert seen["accounts"] == ["3", "4"]


def test_set_category_puts_the_slug_for_the_transaction() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, json={"transaction_id": 4, "source": "manual"})

    client_with(httpx.MockTransport(handler)).set_category(4, "food.groceries")

    assert (seen["method"], seen["path"], seen["json"]) == (
        "PUT",
        "/transactions/4/category",
        {"category": "food.groceries"},
    )


def test_rerun_rules_sends_the_dry_run_flag_and_uncategorized_the_paging() -> None:
    seen: list[tuple[str, str, dict[str, str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, dict(request.url.params)))
        return httpx.Response(200, json={})

    client = client_with(httpx.MockTransport(handler))
    client.rerun_rules(dry_run=True)
    client.uncategorized(25, 50)

    assert seen == [
        ("POST", "/categorization/rerun", {"dry_run": "true"}),
        ("GET", "/transactions/uncategorized", {"limit": "25", "offset": "50"}),
    ]


def test_a_slow_answer_is_a_timeout_not_an_unreachable_api() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    client = client_with(httpx.MockTransport(handler))

    with pytest.raises(ApiTimeoutError, match="did not answer"):
        client.upload_import("march.csv", b"a;b")
    # Pages that only know ApiUnreachableError still handle it.
    with pytest.raises(ApiUnreachableError):
        client.list_accounts()


def test_upload_uses_its_own_longer_timeout() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["timeout"] = request.extensions["timeout"]
        return httpx.Response(201, json={})

    client = ApiClient(
        base_url="http://api.test",
        timeout=5.0,
        upload_timeout=99.0,
        transport=httpx.MockTransport(handler),
    )
    client.upload_import("march.csv", b"a;b")

    assert seen["timeout"] == {"connect": 99.0, "read": 99.0, "write": 99.0, "pool": 99.0}


def test_run_llm_posts_with_the_dry_run_flag() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["query"] = request.url.query
        return httpx.Response(200, json={"evaluated": 3})

    result = client_with(httpx.MockTransport(handler)).run_llm(dry_run=True)

    assert result == {"evaluated": 3}
    assert (seen["method"], seen["path"], seen["query"]) == (
        "POST",
        "/categorization/llm",
        b"dry_run=true",
    )


def test_ask_sends_the_question_and_the_conversation() -> None:
    bodies: list[object] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert (request.method, request.url.path) == ("POST", "/agent/ask")
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"conversation_id": "c1", "status": "answered"})

    client = client_with(httpx.MockTransport(handler))
    first = client.ask("How much?", None)
    client.ask("And then?", "c1")

    assert first["conversation_id"] == "c1"
    assert bodies == [{"question": "How much?"}, {"question": "And then?", "conversation_id": "c1"}]


def test_ask_uses_the_agent_timeout() -> None:
    assert ApiClient().agent_timeout > ApiClient().timeout


def test_forget_conversation_sends_a_delete_and_accepts_no_content() -> None:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        return httpx.Response(204)

    client_with(httpx.MockTransport(handler)).forget_conversation("c1")

    assert seen == [("DELETE", "/agent/conversations/c1")]


def test_ask_maps_503_to_an_api_error_with_the_detail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "LLMUnavailableError", "detail": "down"})

    with pytest.raises(ApiError) as excinfo:
        client_with(httpx.MockTransport(handler)).ask("q", None)

    assert excinfo.value.status_code == 503
    assert excinfo.value.detail == "down"
