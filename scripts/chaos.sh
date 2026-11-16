#!/usr/bin/env bash
# Inject failures to prove the alerts fire (and see them in dashboards/logs/traces).
#   ./scripts/chaos.sh errors    payments returns 30% HTTP 500  -> HighErrorRate (+SLO burn) in ~5-7 min
#   ./scripts/chaos.sh latency   orders adds 1.5s per request   -> HighLatencyP99 in ~5-7 min
#   ./scripts/chaos.sh crash     orders crashes on start        -> PodCrashLooping in ~5-10 min
#   (NodeNotReady and DiskSpaceLow/Critical are proven by promtool unit tests: the laptop
#    profile is a single node, so stopping it would stop Prometheus too, and filling a kind
#    node's disk would fill Docker Desktop's own disk.)
#   ./scripts/chaos.sh reset     undo everything
set -euo pipefail
NS=shop
case "${1:-help}" in
  errors)  kubectl -n $NS set env deploy/payments FAILURE_RATE=0.3 ;;
  latency) kubectl -n $NS set env deploy/orders EXTRA_LATENCY_MS=1500 ;;
  crash)   kubectl -n $NS set env deploy/orders CRASH_ON_START=true ;;
  reset)
    kubectl -n $NS set env deploy/payments FAILURE_RATE=0
    kubectl -n $NS set env deploy/orders EXTRA_LATENCY_MS=0 CRASH_ON_START=false
    echo "reset done" ;;
  *) sed -n '2,8p' "$0" ;;
esac
