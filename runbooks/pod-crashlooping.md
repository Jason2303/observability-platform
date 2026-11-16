# Runbook: PodCrashLooping

| | |
|---|---|
| **Severity** | warning → `#alerts-warning` (critical if it also triggers ServiceDown/HighErrorRate) |
| **Fires when** | A container restarted more than 3 times in the last hour |
| **Impact** | Reduced capacity; if all replicas crash, the service is down |
| **Dashboards** | Shop / Infrastructure → *Containers restarting* |

## 1. Identify
```bash
kubectl get pods -A --field-selector=status.phase!=Succeeded | grep -Ei 'crash|error|backoff'
kubectl -n <ns> describe pod <pod>         # Last State: reason + exit code
```
| Exit code / reason | Usually means |
|---|---|
| `OOMKilled` (137) | Memory limit too low or a memory leak |
| 1 / 2 | Application error on start (bad config, missing env/secret) |
| 137 without OOM | Liveness probe failing, so kubelet kills it |
| `CreateContainerConfigError` | Missing ConfigMap/Secret |

## 2. Read the logs of the crashed attempt
```bash
kubectl -n <ns> logs <pod> --previous
```
Or in Loki: `{namespace="<ns>", pod="<pod>"}` (Alloy keeps logs from earlier attempts).

## 3. Mitigate
| Cause | Action |
|---|---|
| Bad release | `kubectl -n <ns> rollout undo deploy/<name>` |
| OOMKilled | Raise `resources.limits.memory`; investigate a leak with the memory panels |
| Liveness too strict | Increase `initialDelaySeconds` / `failureThreshold` |
| Missing config | Restore the ConfigMap/Secret (via Git) |
| Demo injection | `kubectl -n shop set env deploy/<name> CRASH_ON_START=false` |

## 4. Verify
`kubectl -n <ns> get pods -w` shows Running and Ready with restarts no longer increasing. The alert auto-resolves once the 1-hour window no longer contains more than 3 restarts.
