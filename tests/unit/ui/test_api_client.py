import json

import httpx2 as httpx
import pytest

from api_client import ApiClient, ApiError, ApiUnreachableError


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
