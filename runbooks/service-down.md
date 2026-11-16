# Runbook: ServiceDown

| | |
|---|---|
| **Severity** | critical → `#alerts-critical` |
| **Fires when** | Prometheus can't scrape a shop pod (`up == 0`) for 2 minutes |
| **Impact** | The pod is not serving, or not observable. If all replicas are down, the service is down. |

## Steps
1. `kubectl -n shop get pods -o wide`: Running? Ready? Restarting? If crash looping, see [pod-crashlooping](pod-crashlooping.md).
2. `kubectl -n shop get endpoints <service>`: are there ready endpoints?
3. Pod is running but not scrapeable: `kubectl -n shop port-forward pod/<pod> 8080` and `curl localhost:8080/metrics`.
4. Prometheus side: Prometheus UI → Status → Targets → `serviceMonitor/monitoring/shop` shows the scrape error.
5. Mitigate: roll back the last change, or restart (`kubectl -n shop rollout restart deploy/<service>`).
6. Verify: `up{namespace="shop"} == 1` for all pods and the alert resolves.
