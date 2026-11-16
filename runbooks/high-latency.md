# Runbook: HighLatencyP99

| | |
|---|---|
| **Severity** | warning → `#alerts-warning` |
| **Fires when** | p99 request latency of a service > 1 s for 5 minutes |
| **Impact** | The slowest 1% of users wait > 1 s. Often a leading indicator of timeouts and errors. |
| **Dashboards** | Shop / Service overview (*Duration*), Tempo traces |

## 1. Confirm
```promql
histogram_quantile(0.99, sum by (service, le) (rate(http_request_duration_seconds_bucket{namespace="shop"}[5m])))
```
Is it one service or all? Latency also propagates upstream: frontend's latency includes orders and payments.

## 2. Find the cause
- **Traces (fastest):** Explore → Tempo → `{ resource.service.namespace = "shop" && duration > 1s }`. The waterfall shows which span is slow.
- **Saturation:** Shop / Infrastructure → CPU by namespace; container throttling:
  ```promql
  rate(container_cpu_cfs_throttled_periods_total{namespace="shop"}[5m]) / rate(container_cpu_cfs_periods_total{namespace="shop"}[5m])
  ```
- **Traffic spike?** Compare request rate with the previous day.
- **Injected latency (demo)?** `kubectl -n shop describe deploy/<svc> | grep EXTRA_LATENCY_MS`

## 3. Mitigate
| Cause | Action |
|---|---|
| CPU throttling | Raise CPU limits or add replicas: `kubectl -n shop scale deploy/<svc> --replicas=4` |
| Slow dependency | Escalate to its owner; consider tighter timeouts or caching |
| Bad release | `kubectl -n shop rollout undo deploy/<svc>` |
| Demo injection | `kubectl -n shop set env deploy/<svc> EXTRA_LATENCY_MS=0` |

## 4. Verify
p99 < 500 ms for 10 minutes and the alert resolves. If it coincided with errors, follow [high-error-rate](high-error-rate.md).
