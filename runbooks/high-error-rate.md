# Runbook: HighErrorRate

| | |
|---|---|
| **Severity** | critical → `#alerts-critical` (pages on-call) |
| **Fires when** | > 5% of a service's requests return 5xx for 5 minutes |
| **Impact** | Customers see failed checkouts or pages. Revenue is lost while it lasts. |
| **Dashboards** | Shop / Service overview, Shop / Application logs |

## 1. Confirm (2 min)
1. Open **Shop / Service overview** → *Errors: 5xx ratio by service*. Which service(s) are red?
2. Errors propagate **upstream**: payments → orders → frontend. The **deepest** failing service is usually the cause.
   ```promql
   sum by (service) (rate(http_requests_total{namespace="shop", status=~"5.."}[5m]))
   ```
3. Which route/status? Use the *Requests by route and status* table.

## 2. Find the cause (5 min)
- **Logs:** Shop / Application logs → *Recent errors* (filter by service). Or in Explore (Loki):
  ```logql
  {namespace="shop", service="payments", level="error"}
  ```
- **Traces:** click a `trace_id` in a log line → Tempo shows which span failed and how long each hop took. *Recent error traces* on the overview does the same.
- **Recent change?**
  ```bash
  kubectl -n shop rollout history deploy/<service>
  kubectl -n shop get events --sort-by=.lastTimestamp | tail -20
  kubectl -n shop describe deploy/<service> | grep -A15 Environment   # e.g. FAILURE_RATE set?
  ```
- **Dependency down?** Check `up{namespace="shop"}` and the ServiceDown alert.

## 3. Mitigate
| Cause | Action |
|---|---|
| Bad deploy | `kubectl -n shop rollout undo deploy/<service>` (or `git revert` in the GitOps repo) |
| Bad config/env | Revert the config change. Demo injection: `kubectl -n shop set env deploy/<service> FAILURE_RATE=0` |
| Overloaded | `kubectl -n shop scale deploy/<service> --replicas=4`, then check CPU limits |
| Downstream outage | Fail fast / degrade, and escalate to the owning team |

## 4. Verify and close
- Error ratio < 1% for 10 minutes; alert resolves (Slack shows ✅ RESOLVED).
- Check the error budget impact on **Shop / SLO**.
- Postmortem if the budget burn was > 5% or customers were affected for > 15 minutes.

**Escalation:** on-call SRE → service owner → engineering manager after 30 minutes.
