"""Request signing for the Bifrost Crypto API."""

from __future__ import annotations

import hashlib
import hmac


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sign_request(
    secret: str,
    method: str,
    path: str,
    query: str,
    timestamp: str,
    nonce: str,
    body: str,
) -> str:
    canonical = "\n".join([method, path, query, timestamp, nonce, sha256_hex(body)])
    return hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def timing_safe_equal(left: str, right: str) -> bool:
    if len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)
