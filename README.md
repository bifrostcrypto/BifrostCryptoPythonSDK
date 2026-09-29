# bifrostcrypto

Python client for the Bifrost Crypto API (`https://bridge.bifrostcrypto.com`). Requires Python 3.10.

```bash
pip install bifrostcrypto
```

```python
import os
from bifrostcrypto import Bifrost, verify_webhook

bifrost = Bifrost(
    api_key=os.environ["BIFROST_API_KEY"],
    signing_secret=os.environ.get("BIFROST_SIGNING_SECRET"),
)

payout = bifrost.payouts.create(
    {
        "wallet": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
        "crypto_currency": "USDT",
        "crypto_amount": "100.50",
        "process_by": "crypto_amount",
        "reference_id": "order_12345",
        "network": "Ethereum",
        "feetakenfromamount": 0,
        "webhook_url": "https://your-site.com/webhook",
    },
    idempotency_key="6f1c0c4e-2b1a-4e3a-9c2d-1a2b3c4d5e6f",
)

event = verify_webhook(raw_body, headers, os.environ["BIFROST_WEBHOOK_KEY"])
```

Amounts stay strings. Field names match the API. Pass `signing_secret` only when the key was created with request signing. A payout batch is `create_many`, and fixed wallets live on `fixed_wallets`.
