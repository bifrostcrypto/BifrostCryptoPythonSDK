"""Resource methods. Names follow Python style; the paths match the other SDKs."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote


class Payouts:
    def __init__(self, client: Any) -> None:
        self._client = client

    def create(self, body: dict, idempotency_key: str | None = None) -> dict:
        return self._client.request(
            "POST",
            "/v1/payout",
            body=body,
            idempotency_key=idempotency_key,
            kind="write",
        )["body"]

    def create_many(self, items: list, idempotency_key: str | None = None) -> dict:
        if len(items) < 1 or len(items) > 50:
            from bifrostcrypto.errors import BifrostError

            raise BifrostError(
                400,
                "max_payouts_exceeded",
                "A payout batch must contain between 1 and 50 items",
            )
        return self._client.request(
            "POST",
            "/v1/payout",
            body=list(items),
            idempotency_key=idempotency_key,
            kind="write",
        )["body"]

    def list(self, query: dict | None = None) -> dict:
        return self._client.request("GET", "/v1/list-payout", query=query, kind="read")["body"]

    def retrieve(self, internal_reference: str) -> dict:
        return self._client.request(
            "GET",
            "/v1/check-payout/" + quote(internal_reference, safe=""),
            kind="read",
        )["body"]


class Payins:
    def __init__(self, client: Any) -> None:
        self._client = client

    def create(self, body: dict) -> dict:
        return self._client.request("POST", "/v1/payin", body=body, kind="write")["body"]

    def list(self, query: dict | None = None) -> dict:
        return self._client.request("GET", "/v1/list-payin", query=query, kind="read")["body"]

    def retrieve(self, internal_reference: str) -> dict:
        return self._client.request(
            "GET",
            "/v1/check-payin/" + quote(internal_reference, safe=""),
            kind="read",
        )["body"]


class Balances:
    def __init__(self, client: Any) -> None:
        self._client = client

    def list(self) -> dict:
        return self._client.request("GET", "/v1/balances", kind="read")["body"]


class Statements:
    def __init__(self, client: Any) -> None:
        self._client = client

    def list(self, query: dict | None = None) -> dict:
        return self._client.request("GET", "/v1/statements", query=query, kind="read")["body"]

    def summary(self, query: dict | None = None) -> dict:
        return self._client.request("GET", "/v1/statements/summary", query=query, kind="read")["body"]


class Summary:
    def __init__(self, client: Any) -> None:
        self._client = client

    def retrieve(self) -> dict:
        return self._client.request("GET", "/v1/summary", kind="read")["body"]

    def tokens(self) -> dict:
        return self._client.request("GET", "/v1/summary/tokens", kind="read")["body"]

    def fiats(self) -> dict:
        return self._client.request("GET", "/v1/summary/fiats", kind="read")["body"]


class Prices:
    def __init__(self, client: Any) -> None:
        self._client = client

    def get(self, query: dict) -> dict:
        return self._client.request("GET", "/v1/get-price", query=query, kind="read")["body"]

    def currencies(self) -> dict:
        return self._client.request("GET", "/v1/get-currencies", kind="read")["body"]


class FixedWallets:
    def __init__(self, client: Any) -> None:
        self._client = client

    def supported(self) -> dict:
        return self._client.request("GET", "/v1/fixed-wallets/supported", kind="read")["body"]

    def config(self) -> dict:
        return self._client.request("GET", "/v1/fixed-wallets/config", kind="read")["body"]

    def update_config(self, body: dict) -> dict:
        return self._client.request("PUT", "/v1/fixed-wallets/config", body=body, kind="write")["body"]

    def list(self, query: dict | None = None) -> dict:
        return self._client.request("GET", "/v1/fixed-wallets", query=query, kind="read")["body"]

    def create(self, body: dict) -> dict:
        result = self._client.request("POST", "/v1/fixed-wallets", body=body, kind="write")
        payload = dict(result["body"] or {})
        payload["created"] = result["status"] == 201
        return payload
