"""Small resilient client for the locally hosted Transfermarkt API."""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class ApiError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


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
        min_interval: float = 0.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.min_interval = max(0.0, min_interval)
        self._request_lock = threading.Lock()
        self._last_request_started = 0.0

    def _wait_for_slot(self) -> None:
        if not self.min_interval:
            return
        with self._request_lock:
            now = time.monotonic()
            remaining = self.min_interval - (now - self._last_request_started)
            if remaining > 0:
                time.sleep(remaining)
            self._last_request_started = time.monotonic()

    def get(self, path: str, params: dict[str, Any] | None = None) -> ApiResponse:
        query = urlencode({k: v for k, v in (params or {}).items() if v is not None})
        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                self._wait_for_slot()
                request = Request(url, headers={"Accept": "application/json"})
                with urlopen(request, timeout=self.timeout) as response:
                    status = int(response.status)
                    raw = response.read()
                payload = json.loads(raw.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ApiError(f"Expected JSON object from {url}")
                return ApiResponse(url=url, status=status, payload=payload)
            except HTTPError as exc:
                last_error = ApiError(f"HTTP {exc.code} for {url}", status=exc.code)
                if exc.code < 500 and exc.code != 429:
                    break
            except (URLError, TimeoutError, json.JSONDecodeError, OSError, ApiError) as exc:
                last_error = exc
            if attempt < self.retries:
                time.sleep(self.backoff * (2 ** attempt))
        if isinstance(last_error, ApiError):
            raise last_error
        raise ApiError(str(last_error or f"Request failed for {url}"))
