"""Webhook verification."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Mapping

from bifrostcrypto.errors import WebhookSignatureError
from bifrostcrypto.sign import sha256_hex, timing_safe_equal

TOLERANCE_SECONDS = 300


def _header(headers: Mapping[str, object], name: str) -> str | None:
    target = name.lower()
    for key, value in headers.items():
        if str(key).lower() != target:
            continue
        if isinstance(value, (list, tuple)):
            value = value[0] if value else ""
        trimmed = str(value).strip()
        return trimmed or None
    return None


def verify_webhook(
    raw_body: str | bytes,
    headers: Mapping[str, object],
    key: str,
    now: int | None = None,
    tolerance_seconds: int = TOLERANCE_SECONDS,
) -> dict:
    """Verify a Bifrost webhook and return the parsed event.

    ``raw_body`` must be the exact bytes the signature was computed over.
    """
    signature = _header(headers, "x-bifrost-signature")
    timestamp = _header(headers, "x-bifrost-timestamp")
    delivery = _header(headers, "x-bifrost-delivery")
    if not signature or not timestamp or not delivery:
        raise WebhookSignatureError("missing", "Webhook signature headers are incomplete")

    current = int(time.time()) if now is None else now
    if not timestamp.isdigit() or abs(current - int(timestamp)) > tolerance_seconds:
        raise WebhookSignatureError("stale", "Webhook timestamp is outside the allowed window")

    text = raw_body.decode("utf-8") if isinstance(raw_body, bytes) else raw_body
    canonical = "\n".join(["v1", timestamp, delivery, sha256_hex(text)])
    expected = "v1=" + hmac.new(key.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    if not timing_safe_equal(expected, signature):
        raise WebhookSignatureError("invalid", "Webhook signature does not match")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as cause:
        raise WebhookSignatureError("invalid_json", "Webhook body is not JSON") from cause
    if not isinstance(parsed, dict):
        raise WebhookSignatureError("invalid_json", "Webhook body is not JSON")
    return parsed
