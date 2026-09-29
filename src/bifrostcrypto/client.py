"""HTTP client for the Bifrost Crypto API."""

from __future__ import annotations

import json
import secrets
import time
from collections.abc import Callable
from typing import Any, Optional
from urllib.parse import quote

from bifrostcrypto.errors import BifrostError
from bifrostcrypto.resources import (
    Balances,
    FixedWallets,
    Payins,
    Payouts,
    Prices,
    Statements,
    Summary,
)
from bifrostcrypto.sign import sign_request

BASE_URL = "https://bridge.bifrostcrypto.com"
MAX_RETRIES = 2
DEFAULT_RETRY_DELAY_MS = 1000
REQUEST_TIMEOUT_SECONDS = 30.0

Handler = Callable[[str, str, dict[str, str], Optional[str]], tuple[int, dict[str, str], str]]


def encode_query(query: dict | None) -> str:
    if not query:
        return ""
    parts: list[str] = []
    for key, value in query.items():
        if value is None:
            continue
        parts.append(quote(str(key), safe="") + "=" + quote(_query_text(value), safe=""))
    return "&".join(parts)


def _query_text(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def encode_body(body: object) -> str | None:
    if body is None:
        return None
    return json.dumps(body, separators=(",", ":"), ensure_ascii=False)


class Bifrost:
    def __init__(
        self,
        api_key: str,
        signing_secret: str | None = None,
        base_url: str = BASE_URL,
        handler: Handler | None = None,
        now: Callable[[], int] | None = None,
        nonce: Callable[[], str] | None = None,
        sleep: Callable[[int], None] | None = None,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        if not api_key:
            raise BifrostError(0, "missing_api_key", "api_key is required")
        self.api_key = api_key
        self.signing_secret = signing_secret or None
        self.base_url = base_url.rstrip("/")
        self._handler = handler
        self._now = now or (lambda: int(time.time()))
        self._nonce = nonce or (lambda: secrets.token_hex(16))
        self._sleep = sleep
        self._max_retries = max_retries
        self.payouts = Payouts(self)
        self.payins = Payins(self)
        self.balances = Balances(self)
        self.statements = Statements(self)
        self.summary = Summary(self)
        self.prices = Prices(self)
        self.fixed_wallets = FixedWallets(self)

    def request(
        self,
        method: str,
        path: str,
        query: dict | None = None,
        body: object = None,
        idempotency_key: str | None = None,
        kind: str = "read",
    ) -> dict[str, Any]:
        encoded_query = encode_query(query)
        encoded_body = encode_body(body) if body is not None else None
        url = self.base_url + path + (("?" + encoded_query) if encoded_query else "")
        attempt = 0

        while True:
            headers = {"X-Bifrost-Invoke": self.api_key}
            if encoded_body is not None:
                headers["Content-Type"] = "application/json"
            if idempotency_key:
                headers["Idempotency-Key"] = idempotency_key
            if self.signing_secret:
                timestamp = str(self._now())
                nonce = self._nonce()
                headers["X-Bifrost-Timestamp"] = timestamp
                headers["X-Bifrost-Nonce"] = nonce
                headers["X-Bifrost-Signature"] = sign_request(
                    self.signing_secret,
                    method,
                    path,
                    encoded_query,
                    timestamp,
                    nonce,
                    encoded_body or "",
                )

            try:
                status, response_headers, raw = self._send(method, url, headers, encoded_body)
            except BifrostError:
                raise
            except Exception as cause:
                raise BifrostError(0, "network_error", str(cause)) from cause

            lowered = {str(key).lower(): str(value) for key, value in response_headers.items()}
            try:
                parsed = json.loads(raw) if raw else None
            except json.JSONDecodeError as cause:
                raise BifrostError(status, "invalid_json", "Response body is not JSON", body=raw) from cause

            if 200 <= status < 300:
                return {"status": status, "headers": lowered, "body": parsed}

            error = _to_error(status, parsed, lowered)
            if not _should_retry(status, error.error, attempt, self._max_retries, kind, idempotency_key):
                raise error

            delay = (
                error.retry_after_seconds * 1000
                if status == 429 and error.retry_after_seconds is not None
                else DEFAULT_RETRY_DELAY_MS
            )
            if self._sleep is not None:
                self._sleep(delay)
            else:
                time.sleep(delay / 1000)
            attempt += 1

    def _send(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: str | None,
    ) -> tuple[int, dict[str, str], str]:
        if self._handler is not None:
            return self._handler(method, url, headers, body)

        import httpx

        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = client.request(method, url, headers=headers, content=body)
        return response.status_code, {key: value for key, value in response.headers.items()}, response.text


def _to_error(status: int, parsed: object, headers: dict[str, str]) -> BifrostError:
    record = parsed if isinstance(parsed, dict) else {}
    code = record.get("error") if isinstance(record.get("error"), str) else "http_error"
    message = record.get("message") if isinstance(record.get("message"), str) else code
    retry = _retry_after_seconds(record, headers) if status == 429 else None
    return BifrostError(status, code, message, record.get("details"), parsed, retry)


def _retry_after_seconds(record: dict, headers: dict[str, str]) -> int | None:
    details = record.get("details")
    if isinstance(details, dict) and isinstance(details.get("retry_after_seconds"), int):
        return details["retry_after_seconds"]
    header = headers.get("retry-after")
    if isinstance(header, str) and header.isdigit():
        return int(header)
    return None


def _should_retry(
    status: int,
    error_code: str,
    attempt: int,
    max_retries: int,
    kind: str,
    idempotency_key: str | None,
) -> bool:
    if attempt >= max_retries:
        return False
    if status == 429:
        return kind == "read" or bool(idempotency_key)
    if status == 409 and error_code == "idempotency_key_in_progress" and idempotency_key:
        return True
    if status == 503 and kind == "read":
        return True
    return False
