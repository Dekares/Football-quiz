"""Small resilient client for the locally hosted Transfermarkt API."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class ApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class ApiResponse:
    url: str
    status: int
    payload: dict[str, Any]


class ApiClient:
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float = 30.0,
        retries: int = 2,
        backoff: float = 1.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff

    def get(self, path: str, params: dict[str, Any] | None = None) -> ApiResponse:
        query = urlencode({k: v for k, v in (params or {}).items() if v is not None})
        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                request = Request(url, headers={"Accept": "application/json"})
                with urlopen(request, timeout=self.timeout) as response:
                    status = int(response.status)
                    raw = response.read()
                payload = json.loads(raw.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ApiError(f"Expected JSON object from {url}")
                return ApiResponse(url=url, status=status, payload=payload)
            except HTTPError as exc:
                last_error = ApiError(f"HTTP {exc.code} for {url}")
                if exc.code < 500 and exc.code != 429:
                    break
            except (URLError, TimeoutError, json.JSONDecodeError, OSError, ApiError) as exc:
                last_error = exc
            if attempt < self.retries:
                time.sleep(self.backoff * (2 ** attempt))
        raise ApiError(str(last_error or f"Request failed for {url}"))
