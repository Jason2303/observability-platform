# Runbook: PaymentDeclinesElevated (info)

| | |
|---|---|
| **Severity** | info → `#alerts-info` (no page) |
| **Fires when** | More than 5% of orders are declined by the payment provider for 15 minutes (baseline is about 1%) |
| **Impact** | Lost sales. Not a technical outage: the system is working, cards are being refused. |

## Steps
1. **Shop / Service overview → Orders by result:** a sudden jump, or a gradual one?
2. Logs: `{namespace="shop", service="orders"} |= "declined"`. Is there a pattern (amount, time)?
3. Sudden jump: check the payment provider's status page; possible fraud-rule change or attack (card testing).
4. Notify the payments/business owner in `#payments`. No engineering action unless a code change caused it (check recent deploys of `payments`).
