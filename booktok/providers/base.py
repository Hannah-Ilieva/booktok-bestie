from __future__ import annotations

from threading import Lock
from pathlib import Path
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


class ProviderError(RuntimeError):
    pass


class JsonProvider:
    provider_name = "provider"
    minimum_request_gap = 1.0

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": "BookTokBestie/0.2 (local single-user book discovery)"}
        )
        retry = Retry(
            total=2,
            connect=2,
            read=2,
            status=2,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "POST"}),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=2, pool_maxsize=2)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)
        self._lock = Lock()
        self._last_request = 0.0

    def request_json(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        with self._lock:
            wait_for = self.minimum_request_gap - (time.monotonic() - self._last_request)
            if wait_for > 0:
                time.sleep(wait_for)
            try:
                response = self._session.request(
                    method,
                    url,
                    timeout=(4, 12),
                    **kwargs,
                )
                self._last_request = time.monotonic()
            except requests.RequestException as exc:
                raise ProviderError(f"{self.provider_name} could not be reached.") from exc

        if response.status_code >= 400:
            raise ProviderError(
                f"{self.provider_name} returned HTTP {response.status_code}. Try again later."
            )
        try:
            payload = response.json()
        except requests.JSONDecodeError as exc:
            raise ProviderError(f"{self.provider_name} returned an unreadable response.") from exc
        if not isinstance(payload, dict):
            raise ProviderError(f"{self.provider_name} returned an unexpected response shape.")
        return payload
