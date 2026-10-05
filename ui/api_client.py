"""HTTP client for the Kontor API. The UI talks to the API only through this module."""

import os
from dataclasses import dataclass
from typing import Any  # Any: JSON bodies are untyped by nature

import httpx2 as httpx

DEFAULT_API_URL = "http://localhost:8000"


class ApiError(Exception):
    """The API answered with an error. `detail` is the readable message."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class ApiUnreachableError(Exception):
    """The API cannot be reached."""


@dataclass(frozen=True, slots=True)
class ApiClient:
    base_url: str = DEFAULT_API_URL
    timeout: float = 300.0  # an upload runs the LLM step synchronously (CONTRACT §8.2)
    transport: httpx.BaseTransport | None = None

    @classmethod
    def from_env(cls) -> "ApiClient":
        return cls(base_url=os.environ.get("API_URL", DEFAULT_API_URL))

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            with httpx.Client(
                base_url=self.base_url, timeout=self.timeout, transport=self.transport
            ) as client:
                response = client.request(method, path, **kwargs)
        except httpx.TransportError as exc:
            raise ApiUnreachableError(f"cannot reach the API at {self.base_url}") from exc
        if response.is_error:
            raise ApiError(response.status_code, _detail(response))
        return response.json()

    def upload_import(self, file_name: str, content: bytes) -> dict[str, Any]:
        files = {"file": (file_name, content, "text/csv")}
        result: dict[str, Any] = self._request("POST", "/imports", files=files)
        return result

    def list_imports(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = self._request("GET", "/imports")
        return result

    def list_accounts(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = self._request("GET", "/accounts")
        return result

    def update_account(self, account_id: int, changes: dict[str, str]) -> dict[str, Any]:
        result: dict[str, Any] = self._request("PATCH", f"/accounts/{account_id}", json=changes)
        return result


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, str):
        return detail
    return f"HTTP {response.status_code}"
