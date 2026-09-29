"""Errors raised by the Bifrost Crypto client."""

from __future__ import annotations


class BifrostError(Exception):
    def __init__(
        self,
        status: int,
        error: str,
        message: str,
        details: object = None,
        body: object = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.error = error
        self.details = details
        self.body = body
        self.retry_after_seconds = retry_after_seconds


class WebhookSignatureError(Exception):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
