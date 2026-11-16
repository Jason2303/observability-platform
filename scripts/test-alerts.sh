#!/usr/bin/env bash
# Validates and unit-tests the alert rules with promtool (no cluster needed).
# Uses a local promtool if installed, otherwise runs it from the Prometheus Docker image
# (works from Git Bash on Windows too).
set -euo pipefail
cd "$(dirname "$0")/.."

# tests/rules.generated.yaml = the .spec of the PrometheusRule (committed; regenerated if yq is present)
if command -v yq >/dev/null 2>&1 && yq --version 2>&1 | grep -q mikefarah; then
  yq '.spec' manifests/alerting/shop-rules.yaml > tests/rules.generated.yaml
fi

if command -v promtool >/dev/null 2>&1; then
  promtool check rules tests/rules.generated.yaml
  promtool test rules tests/alerts.test.yaml
else
  HOSTDIR="$(pwd -W 2>/dev/null || pwd)"   # pwd -W gives C:/... in Git Bash
  run() { MSYS_NO_PATHCONV=1 docker run --rm -v "$HOSTDIR:/work" -w /work \
            --entrypoint promtool prom/prometheus:v3.5.0 "$@"; }
  run check rules tests/rules.generated.yaml
  run test rules tests/alerts.test.yaml
fi
