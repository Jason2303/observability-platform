#!/usr/bin/env bash
# One-command install of the whole platform on a kind cluster.
#   ./scripts/setup.sh                      # create cluster "obs" and install everything
#   SKIP_CLUSTER=1 ./scripts/setup.sh       # use the current kubectl context instead
#   SLACK_WEBHOOK_URL=https://hooks.slack.com/... ./scripts/setup.sh   # real Slack alerts
# Needs: docker, kind, kubectl, helm, openssl
set -euo pipefail
cd "$(dirname "$0")/.."

CLUSTER=obs
step() { echo; echo "==> $*"; }

if [ "${SKIP_CLUSTER:-0}" != "1" ]; then
  others="$(kind get clusters 2>/dev/null | grep -vx "$CLUSTER" || true)"
  if [ -n "$others" ]; then
    echo "!! Other kind clusters are running: $others"
    echo "!! On a 5 GB Docker/WSL limit, stop them first:  docker stop \$(docker ps -q --filter name=<cluster>-)"
  fi
  step "kind cluster '$CLUSTER'"
  kind get clusters | grep -qx "$CLUSTER" || kind create cluster --config kind/kind-config.yaml
  kubectl config use-context "kind-$CLUSTER"
fi

step "Namespaces"
kubectl apply -f manifests/namespaces.yaml

step "Secrets (generated here - never stored in Git)"
if ! kubectl -n monitoring get secret grafana-admin >/dev/null 2>&1; then
  GRAFANA_PW="$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)"
  kubectl -n monitoring create secret generic grafana-admin \
    --from-literal=admin-user=admin --from-literal=admin-password="$GRAFANA_PW"
fi
# Slack webhook for Alertmanager. Placeholder if not provided (alerts still visible in Alertmanager UI).
kubectl -n monitoring create secret generic alertmanager-slack \
  --from-literal=webhook-url="${SLACK_WEBHOOK_URL:-https://hooks.slack.com/services/NOT/CONFIGURED/YET}" \
  --dry-run=client -o yaml | kubectl apply -f -

step "Helm repositories"
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null
helm repo add grafana https://grafana.github.io/helm-charts >/dev/null
helm repo add grafana-community https://grafana-community.github.io/helm-charts >/dev/null
helm repo update >/dev/null

step "Metrics + alerting + dashboards: kube-prometheus-stack (monitoring)"
helm upgrade --install kps prometheus-community/kube-prometheus-stack -n monitoring \
  -f helm/kube-prometheus-stack-values.yaml --wait --timeout 25m

step "Logs: Loki (observability)"
helm upgrade --install loki grafana/loki -n observability \
  -f helm/loki-values.yaml --wait --timeout 25m

step "Traces: Tempo (observability)"
helm upgrade --install tempo grafana-community/tempo -n observability \
  -f helm/tempo-values.yaml --wait --timeout 25m

step "Log collection: Grafana Alloy (observability)"
helm upgrade --install alloy grafana/alloy -n observability \
  -f helm/alloy-values.yaml --wait --timeout 15m

step "Build the shop app image and load it into kind"
docker build -t shop-app:1.0 app/
kind load docker-image shop-app:1.0 --name "$CLUSTER" 2>/dev/null || \
  echo "   (not a kind cluster named $CLUSTER: push shop-app:1.0 to a registry your cluster can pull from)"

step "Shop app, alert rules, dashboards"
kubectl apply -k manifests/app
kubectl apply -f manifests/alerting/shop-rules.yaml
kubectl apply --server-side -k dashboards/
kubectl -n shop rollout status deploy/frontend --timeout=180s

cat <<EOF

==================================================================
 Done. Open each UI in its own terminal:

   Grafana       kubectl -n monitoring port-forward svc/kps-grafana 3000:80
                 http://localhost:3000   user: admin
                 password: kubectl -n monitoring get secret grafana-admin -o jsonpath='{.data.admin-password}' | base64 -d
   Prometheus    kubectl -n monitoring port-forward svc/kps-prometheus 9090
   Alertmanager  kubectl -n monitoring port-forward svc/kps-alertmanager 9093

 Dashboards: Grafana -> Dashboards -> Shop
 Trigger alerts: ./scripts/chaos.sh help
==================================================================
EOF
