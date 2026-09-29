import json
import unittest
from pathlib import Path

from bifrostcrypto import (
    BASE_URL,
    Bifrost,
    BifrostError,
    WebhookSignatureError,
    sign_request,
    verify_webhook,
)

CONTRACT = Path(__file__).resolve().parents[1] / "contract"
SIGNATURE = json.loads((CONTRACT / "signature.json").read_text())
WEBHOOK = json.loads((CONTRACT / "webhook.json").read_text())
HTTP = json.loads((CONTRACT / "http.json").read_text())


def json_response(status, body):
    return status, {"content-type": "application/json"}, json.dumps(body, separators=(",", ":"))


def ok():
    return json_response(200, {"message": "ok"})


def sample_payout(reference):
    return {
        "wallet": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
        "crypto_currency": "USDT",
        "crypto_amount": "1.00",
        "process_by": "crypto_amount",
        "reference_id": reference,
        "network": "Ethereum",
        "feetakenfromamount": 0,
        "webhook_url": "https://example.com/hook",
    }


class SignatureTest(unittest.TestCase):
    def test_vectors(self):
        for vector in SIGNATURE["vectors"]:
            actual = sign_request(
                SIGNATURE["secret"],
                vector["method"],
                vector["path"],
                vector["query"],
                vector["timestamp"],
                vector["nonce"],
                vector["body"],
            )
            self.assertEqual(actual, vector["signature"], vector["id"])


class WebhookTest(unittest.TestCase):
    def headers(self, signature=None):
        return {
            "X-Bifrost-Signature": WEBHOOK["signature"] if signature is None else signature,
            "X-Bifrost-Timestamp": WEBHOOK["timestamp"],
            "X-Bifrost-Delivery": WEBHOOK["delivery"],
        }

    def test_valid(self):
        event = verify_webhook(WEBHOOK["raw_body"], self.headers(), WEBHOOK["key"], now=WEBHOOK["now"])
        self.assertEqual(event["event"], WEBHOOK["expected_event"])
        self.assertEqual(event["data"]["reference_id"], "order_12345")

    def test_window_edge(self):
        event = verify_webhook(
            WEBHOOK["raw_body"],
            self.headers(),
            WEBHOOK["key"],
            now=WEBHOOK["within_window_now"],
        )
        self.assertEqual(event["event"], WEBHOOK["expected_event"])

    def test_stale(self):
        with self.assertRaises(WebhookSignatureError) as caught:
            verify_webhook(WEBHOOK["raw_body"], self.headers(), WEBHOOK["key"], now=WEBHOOK["stale_now"])
        self.assertEqual(caught.exception.reason, "stale")

    def test_bad_signature(self):
        with self.assertRaises(WebhookSignatureError) as caught:
            verify_webhook(
                WEBHOOK["raw_body"],
                self.headers(WEBHOOK["bad_signature"]),
                WEBHOOK["key"],
                now=WEBHOOK["now"],
            )
        self.assertEqual(caught.exception.reason, "invalid")

    def test_missing(self):
        with self.assertRaises(WebhookSignatureError) as caught:
            verify_webhook(WEBHOOK["raw_body"], {}, WEBHOOK["key"], now=WEBHOOK["now"])
        self.assertEqual(caught.exception.reason, "missing")


class ClientTest(unittest.TestCase):
    def test_base_url(self):
        self.assertEqual(BASE_URL, HTTP["base_url"])

    def test_unsigned_request(self):
        calls = []

        def handler(method, url, headers, body):
            calls.append((method, url, headers, body))
            return json_response(HTTP["balances_ok"]["status"], HTTP["balances_ok"]["body"])

        bifrost = Bifrost(api_key=HTTP["api_key"], handler=handler)
        balances = bifrost.balances.list()
        self.assertEqual(balances["balances"]["balance_tether"], "1000.00000000")
        self.assertEqual(calls[0][0], "GET")
        self.assertEqual(calls[0][1], HTTP["base_url"] + HTTP["paths"]["balances"])
        self.assertEqual(calls[0][2]["X-Bifrost-Invoke"], HTTP["api_key"])
        self.assertNotIn("X-Bifrost-Signature", calls[0][2])
        self.assertIsNone(calls[0][3])

    def test_signed_payout(self):
        vector = next(item for item in SIGNATURE["vectors"] if item["id"] == "post_with_body")
        calls = []

        def handler(method, url, headers, body):
            calls.append((method, url, headers, body))
            return json_response(200, {"message": "payment_processing_completed", "results": []})

        bifrost = Bifrost(
            api_key=HTTP["api_key"],
            signing_secret=SIGNATURE["secret"],
            now=lambda: int(vector["timestamp"]),
            nonce=lambda: vector["nonce"],
            handler=handler,
        )
        bifrost.payouts.create(json.loads(vector["body"]), idempotency_key="idem-1")
        self.assertEqual(calls[0][3], vector["body"])
        self.assertEqual(calls[0][2]["X-Bifrost-Signature"], vector["signature"])
        self.assertEqual(calls[0][2]["Idempotency-Key"], "idem-1")

    def test_signed_price(self):
        vector = next(item for item in SIGNATURE["vectors"] if item["id"] == "get_with_query")
        calls = []

        def handler(method, url, headers, body):
            calls.append((method, url, headers, body))
            return ok()

        bifrost = Bifrost(
            api_key=HTTP["api_key"],
            signing_secret=SIGNATURE["secret"],
            now=lambda: int(vector["timestamp"]),
            nonce=lambda: vector["nonce"],
            handler=handler,
        )
        bifrost.prices.get({"currency1": "USDT", "currency2": "USD"})
        self.assertEqual(calls[0][1], HTTP["base_url"] + vector["path"] + "?" + vector["query"])
        self.assertEqual(calls[0][2]["X-Bifrost-Signature"], vector["signature"])
        self.assertIsNone(calls[0][3])

    def test_routes(self):
        calls = []

        def handler(method, url, headers, body):
            calls.append(method + " " + url)
            path = url.split("?", 1)[0]
            if path.endswith(HTTP["paths"]["fixed_wallets"]) and method == "POST":
                return json_response(HTTP["fixed_wallet_created"]["status"], HTTP["fixed_wallet_created"]["body"])
            return ok()

        bifrost = Bifrost(api_key=HTTP["api_key"], handler=handler)
        payout = sample_payout("order_1")
        bifrost.payouts.create(payout)
        bifrost.payouts.create_many([payout])
        bifrost.payouts.list({"page": 2, "status": "PENDING"})
        bifrost.payouts.retrieve("BIFROST_REF_123456")
        bifrost.payins.create(
            {
                "crypto_currency": "USDT",
                "crypto_amount": "1.00",
                "process_by": "crypto_amount",
                "reference_id": "invoice_1",
                "network": "Ethereum",
                "webhook_url": "https://example.com/hook",
            }
        )
        bifrost.payins.list()
        bifrost.payins.retrieve("ref/with slash")
        bifrost.balances.list()
        bifrost.statements.list({"direction": "out"})
        bifrost.statements.summary({"date_from": "2026-01-01"})
        bifrost.summary.retrieve()
        bifrost.summary.tokens()
        bifrost.summary.fiats()
        bifrost.prices.get({"currency1": "USDT", "currency2": "USD"})
        bifrost.prices.currencies()
        bifrost.fixed_wallets.supported()
        bifrost.fixed_wallets.config()
        bifrost.fixed_wallets.update_config({"webhook_url": "https://example.com/wallets"})
        bifrost.fixed_wallets.list({"limit": 10, "offset": 0})
        created = bifrost.fixed_wallets.create({"type": "evm", "customer_info": "customer123"})

        base = HTTP["base_url"]
        paths = HTTP["paths"]
        expected = [
            "POST " + base + paths["payout"],
            "POST " + base + paths["payout"],
            "GET " + base + paths["list_payout"] + "?page=2&status=PENDING",
            "GET " + base + paths["check_payout"] + "/BIFROST_REF_123456",
            "POST " + base + paths["payin"],
            "GET " + base + paths["list_payin"],
            "GET " + base + paths["check_payin"] + "/ref%2Fwith%20slash",
            "GET " + base + paths["balances"],
            "GET " + base + paths["statements"] + "?direction=out",
            "GET " + base + paths["statements_summary"] + "?date_from=2026-01-01",
            "GET " + base + paths["summary"],
            "GET " + base + paths["tokens"],
            "GET " + base + paths["fiats"],
            "GET " + base + paths["price"] + "?currency1=USDT&currency2=USD",
            "GET " + base + paths["currencies"],
            "GET " + base + paths["fixed_supported"],
            "GET " + base + paths["fixed_config"],
            "PUT " + base + paths["fixed_config"],
            "GET " + base + paths["fixed_wallets"] + "?limit=10&offset=0",
            "POST " + base + paths["fixed_wallets"],
        ]
        self.assertEqual(calls, expected)
        self.assertTrue(created["created"])

    def test_partial_batch(self):
        bifrost = Bifrost(
            api_key=HTTP["api_key"],
            handler=lambda *args: json_response(HTTP["partial_batch"]["status"], HTTP["partial_batch"]["body"]),
        )
        result = bifrost.payouts.create_many([sample_payout("a"), sample_payout("b")])
        self.assertEqual(result["summary"]["failed"], 1)
        self.assertEqual(result["results"][1]["index"], 1)

    def test_processing_exception(self):
        bifrost = Bifrost(
            api_key=HTTP["api_key"],
            handler=lambda *args: json_response(
                HTTP["processing_exception"]["status"],
                HTTP["processing_exception"]["body"],
            ),
        )
        with self.assertRaises(BifrostError) as caught:
            bifrost.payouts.create_many([sample_payout("a")], idempotency_key="idem-1")
        self.assertEqual(caught.exception.error, "processing_exception")
        self.assertEqual(caught.exception.body["summary"]["not_processed"], 18)

    def test_read_retries_429(self):
        sleeps = []
        calls = {"n": 0}

        def handler(*args):
            calls["n"] += 1
            if calls["n"] == 1:
                return json_response(HTTP["rate_limit"]["status"], HTTP["rate_limit"]["body"])
            return json_response(HTTP["balances_ok"]["status"], HTTP["balances_ok"]["body"])

        bifrost = Bifrost(api_key=HTTP["api_key"], handler=handler, sleep=sleeps.append)
        balances = bifrost.balances.list()
        self.assertEqual(calls["n"], 2)
        self.assertEqual(sleeps[0], HTTP["rate_limit"]["body"]["details"]["retry_after_seconds"] * 1000)
        self.assertEqual(balances["message"], "balances_retrieved_success")

    def test_write_without_idempotency_is_not_retried(self):
        calls = {"n": 0}

        def handler(*args):
            calls["n"] += 1
            return json_response(HTTP["rate_limit"]["status"], HTTP["rate_limit"]["body"])

        bifrost = Bifrost(api_key=HTTP["api_key"], handler=handler)
        with self.assertRaises(BifrostError) as caught:
            bifrost.payouts.create(sample_payout("a"))
        self.assertEqual(caught.exception.retry_after_seconds, 24)
        self.assertEqual(calls["n"], 1)

    def test_write_with_idempotency_retries_429(self):
        sleeps = []
        calls = {"n": 0}

        def handler(*args):
            calls["n"] += 1
            if calls["n"] == 1:
                return json_response(HTTP["rate_limit"]["status"], HTTP["rate_limit"]["body"])
            return json_response(200, {"message": "payment_processing_completed"})

        bifrost = Bifrost(api_key=HTTP["api_key"], handler=handler, sleep=sleeps.append)
        bifrost.payouts.create(sample_payout("a"), idempotency_key="idem-1")
        self.assertEqual(calls["n"], 2)
        self.assertEqual(sleeps[0], 24000)

    def test_idempotency_in_progress(self):
        keys = []
        sleeps = []
        calls = {"n": 0}

        def handler(method, url, headers, body):
            calls["n"] += 1
            keys.append(headers.get("Idempotency-Key"))
            if calls["n"] == 1:
                return json_response(HTTP["idempotency_in_progress"]["status"], HTTP["idempotency_in_progress"]["body"])
            return json_response(200, {"message": "payment_processing_completed"})

        bifrost = Bifrost(api_key=HTTP["api_key"], handler=handler, sleep=sleeps.append)
        bifrost.payouts.create(sample_payout("a"), idempotency_key="idem-1")
        self.assertEqual(keys, ["idem-1", "idem-1"])
        self.assertEqual(sleeps[0], HTTP["default_retry_delay_ms"])

    def test_503(self):
        reads = {"n": 0}
        writes = {"n": 0}

        def handler(method, url, headers, body):
            if method == "GET":
                reads["n"] += 1
                if reads["n"] == 1:
                    return json_response(HTTP["service_unavailable"]["status"], HTTP["service_unavailable"]["body"])
                return ok()
            writes["n"] += 1
            return json_response(HTTP["service_unavailable"]["status"], HTTP["service_unavailable"]["body"])

        bifrost = Bifrost(api_key=HTTP["api_key"], handler=handler, sleep=lambda ms: None)
        bifrost.balances.list()
        self.assertEqual(reads["n"], 2)
        with self.assertRaises(BifrostError):
            bifrost.payins.create(
                {
                    "crypto_currency": "USDT",
                    "process_by": "crypto_amount",
                    "reference_id": "invoice_1",
                    "network": "Ethereum",
                    "webhook_url": "https://example.com/hook",
                    "crypto_amount": "1.00",
                }
            )
        self.assertEqual(writes["n"], 1)

    def test_retry_cap(self):
        calls = {"n": 0}

        def handler(*args):
            calls["n"] += 1
            return json_response(HTTP["rate_limit"]["status"], HTTP["rate_limit"]["body"])

        bifrost = Bifrost(api_key=HTTP["api_key"], handler=handler, sleep=lambda ms: None)
        with self.assertRaises(BifrostError):
            bifrost.balances.list()
        self.assertEqual(calls["n"], HTTP["max_retries"] + 1)

    def test_batch_limit(self):
        calls = {"n": 0}

        def handler(*args):
            calls["n"] += 1
            return ok()

        bifrost = Bifrost(api_key=HTTP["api_key"], handler=handler)
        items = [sample_payout(str(index)) for index in range(HTTP["max_payouts"] + 1)]
        with self.assertRaises(BifrostError) as caught:
            bifrost.payouts.create_many(items)
        self.assertEqual(caught.exception.error, "max_payouts_exceeded")
        self.assertEqual(calls["n"], 0)

    def test_existing_fixed_wallet(self):
        bifrost = Bifrost(
            api_key=HTTP["api_key"],
            handler=lambda *args: json_response(
                HTTP["fixed_wallet_existing"]["status"],
                HTTP["fixed_wallet_existing"]["body"],
            ),
        )
        existing = bifrost.fixed_wallets.create({"type": "evm", "customer_info": "customer123"})
        self.assertFalse(existing["created"])
        self.assertEqual(existing["message"], "FixedWallets.already_assigned")


if __name__ == "__main__":
    unittest.main()
