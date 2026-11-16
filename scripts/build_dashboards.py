#!/usr/bin/env python3
"""Dashboards as code: generates the Grafana dashboard JSON exports in dashboards/.

    python3 scripts/build_dashboards.py

Datasource UIDs are fixed in helm/kube-prometheus-stack-values.yaml:
prometheus, loki, tempo.
"""
import json
import pathlib

OUT = pathlib.Path(__file__).resolve().parent.parent / "dashboards"
PROM = {"type": "prometheus", "uid": "prometheus"}
LOKI = {"type": "loki", "uid": "loki"}
TEMPO = {"type": "tempo", "uid": "tempo"}

_id = 0


def _next_id():
    global _id
    _id += 1
    return _id


def target(expr, legend="", ds=PROM, ref="A", **extra):
    t = {"datasource": ds, "expr": expr, "refId": ref, "legendFormat": legend}
    t.update(extra)
    return t


def panel(kind, title, targets, x, y, w, h, ds=PROM, unit=None, desc="", thresholds=None,
          options=None, overrides=None, min_=None, max_=None, decimals=None):
    defaults = {"custom": {}}
    if unit:
        defaults["unit"] = unit
    if min_ is not None:
        defaults["min"] = min_
    if max_ is not None:
        defaults["max"] = max_
    if decimals is not None:
        defaults["decimals"] = decimals
    if thresholds:
        defaults["thresholds"] = {
            "mode": "absolute",
            "steps": [{"color": c, "value": v} for v, c in thresholds],
        }
        if kind == "timeseries":
            defaults["custom"]["thresholdsStyle"] = {"mode": "line+area"}
    if kind == "timeseries":
        defaults["custom"].update({"lineWidth": 2, "fillOpacity": 10, "showPoints": "never"})
    p = {
        "id": _next_id(),
        "type": kind,
        "title": title,
        "description": desc,
        "datasource": ds,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "targets": targets,
        "fieldConfig": {"defaults": defaults, "overrides": overrides or []},
        "options": options or {},
    }
    if kind == "stat":
        p["options"] = {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                        "colorMode": "background", "graphMode": "area", "textMode": "auto", **(options or {})}
    if kind == "timeseries":
        p["options"] = {"legend": {"displayMode": "table", "placement": "bottom", "calcs": ["mean", "max", "lastNotNull"]},
                        "tooltip": {"mode": "multi", "sort": "desc"}, **(options or {})}
    return p


def row(title, y):
    return {"id": _next_id(), "type": "row", "title": title, "collapsed": False,
            "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}, "panels": []}


def dashboard(uid, title, panels, templating=None, tags=None, desc="", refresh="30s", time_from="now-1h"):
    return {
        "uid": uid,
        "title": title,
        "description": desc,
        "tags": tags or [],
        "timezone": "browser",
        "schemaVersion": 39,
        "version": 1,
        "editable": True,
        "graphTooltip": 1,
        "refresh": refresh,
        "time": {"from": time_from, "to": "now"},
        "templating": {"list": templating or []},
        "annotations": {"list": [{
            "builtIn": 1, "datasource": {"type": "grafana", "uid": "-- Grafana --"},
            "enable": True, "hide": True, "iconColor": "rgba(0, 211, 255, 1)",
            "name": "Annotations & Alerts", "type": "dashboard"}]},
        "links": [{"title": "Shop dashboards", "type": "dashboards", "tags": ["shop"], "asDropdown": True}],
        "panels": panels,
    }


def prom_var(name, query, label, multi=True):
    return {
        "name": name, "label": label, "type": "query", "datasource": PROM,
        "query": {"query": query, "refId": "PrometheusVariableQueryEditor-VariableQuery"},
        "definition": query, "refresh": 2, "includeAll": multi, "multi": multi,
        "allValue": ".*", "current": {"selected": True, "text": "All", "value": "$__all"} if multi else {},
        "sort": 1,
    }


# ====================================================================== 1. RED
def service_overview():
    global _id
    _id = 0
    sel = 'namespace="shop", service=~"$service"'
    p = [row("RED: rate, errors, duration", 0)]
    p += [
        panel("stat", "Request rate", [target(f'sum(rate(http_requests_total{{{sel}}}[5m]))', "req/s")],
              0, 1, 6, 4, unit="reqps", decimals=1, thresholds=[(None, "blue")]),
        panel("stat", "Error rate (5xx)", [target(
            f'sum(rate(http_requests_total{{{sel}, status=~"5.."}}[5m])) / sum(rate(http_requests_total{{{sel}}}[5m]))')],
            6, 1, 6, 4, unit="percentunit", decimals=2,
            thresholds=[(None, "green"), (0.01, "orange"), (0.05, "red")],
            desc="Alert HighErrorRate fires above 5% for 5m"),
        panel("stat", "p99 latency", [target(
            f'histogram_quantile(0.99, sum by (le) (rate(http_request_duration_seconds_bucket{{{sel}}}[5m])))')],
            12, 1, 6, 4, unit="s", decimals=3,
            thresholds=[(None, "green"), (0.5, "orange"), (1, "red")],
            desc="Alert HighLatencyP99 fires above 1s for 5m"),
        panel("stat", "Healthy pods", [target('sum(up{namespace="shop", service=~"$service"})')],
              18, 1, 6, 4, thresholds=[(None, "red"), (1, "green")]),
        panel("timeseries", "Rate: requests per second by service",
              [target(f'sum by (service) (rate(http_requests_total{{{sel}}}[5m]))', "{{service}}")],
              0, 5, 8, 8, unit="reqps"),
        panel("timeseries", "Errors: 5xx ratio by service",
              [target(f'sum by (service) (rate(http_requests_total{{{sel}, status=~"5.."}}[5m])) '
                      f'/ sum by (service) (rate(http_requests_total{{{sel}}}[5m]))', "{{service}}")],
              8, 5, 8, 8, unit="percentunit", min_=0,
              thresholds=[(None, "transparent"), (0.05, "red")]),
        panel("timeseries", "Duration: latency percentiles",
              [target(f'histogram_quantile(0.50, sum by (service, le) (rate(http_request_duration_seconds_bucket{{{sel}}}[5m])))', "p50 {{service}}", ref="A"),
               target(f'histogram_quantile(0.95, sum by (service, le) (rate(http_request_duration_seconds_bucket{{{sel}}}[5m])))', "p95 {{service}}", ref="B"),
               target(f'histogram_quantile(0.99, sum by (service, le) (rate(http_request_duration_seconds_bucket{{{sel}}}[5m])))', "p99 {{service}}", ref="C")],
              16, 5, 8, 8, unit="s", thresholds=[(None, "transparent"), (1, "red")]),
        panel("table", "Requests by route and status (last 5m rate)",
              [target(f'sum by (service, route, method, status) (rate(http_requests_total{{{sel}}}[5m]))',
                      format="table", instant=True)],
              0, 13, 12, 8, unit="reqps", decimals=2,
              options={"showHeader": True, "sortBy": [{"displayName": "Value", "desc": True}]}),
        panel("table", "Recent error traces (Tempo)",
              [{"datasource": TEMPO, "refId": "A", "queryType": "traceql", "limit": 20, "tableType": "traces",
                "query": '{ resource.service.namespace = "shop" && status = error }'}],
              12, 13, 12, 8, ds=TEMPO, desc="Click a trace ID to open it; from a span jump to its logs in Loki"),
    ]
    p.append(row("Business metrics", 21))
    p += [
        panel("stat", "Orders / min", [target('sum(rate(shop_orders_total{namespace="shop", result="success"}[5m])) * 60')],
              0, 22, 6, 4, decimals=1, thresholds=[(None, "blue")]),
        panel("stat", "Revenue / hour", [target('sum(rate(shop_revenue_usd_total{namespace="shop"}[5m])) * 3600')],
              6, 22, 6, 4, unit="currencyUSD", decimals=0, thresholds=[(None, "green")]),
        panel("stat", "Order success rate", [target(
            'sum(rate(shop_orders_total{namespace="shop", result="success"}[5m])) / sum(rate(shop_orders_total{namespace="shop"}[5m]))')],
            12, 22, 6, 4, unit="percentunit", decimals=1,
            thresholds=[(None, "red"), (0.95, "orange"), (0.98, "green")]),
        panel("stat", "Avg order value", [target(
            'sum(rate(shop_cart_value_usd_sum{namespace="shop"}[15m])) / sum(rate(shop_cart_value_usd_count{namespace="shop"}[15m]))')],
            18, 22, 6, 4, unit="currencyUSD", decimals=2, thresholds=[(None, "purple")]),
        panel("timeseries", "Orders by result",
              [target('sum by (result) (rate(shop_orders_total{namespace="shop"}[5m])) * 60', "{{result}}")],
              0, 26, 12, 8, unit="short", desc="Orders per minute: success / declined / failed"),
        panel("timeseries", "Revenue per minute (USD)",
              [target('sum(rate(shop_revenue_usd_total{namespace="shop"}[5m])) * 60', "revenue/min")],
              12, 26, 12, 8, unit="currencyUSD"),
    ]
    return dashboard("shop-service-overview", "Shop / Service overview (RED + business)", p,
                     templating=[prom_var("service", 'label_values(http_requests_total{namespace="shop"}, service)', "Service")],
                     tags=["shop", "red"], desc="RED method per service, plus business KPIs and error traces")


# ============================================================ 2. Infrastructure
def infrastructure():
    global _id
    _id = 0
    inst = 'instance=~"$instance"'
    fs = 'fstype!~"tmpfs|overlay|squashfs|ramfs|nsfs"'
    p = [row("Nodes", 0)]
    p += [
        panel("stat", "Nodes Ready", [target('sum(kube_node_status_condition{condition="Ready", status="true"})')],
              0, 1, 4, 4, thresholds=[(None, "red"), (1, "green")]),
        panel("stat", "CPU used", [target(f'1 - avg(rate(node_cpu_seconds_total{{mode="idle", {inst}}}[5m]))')],
              4, 1, 5, 4, unit="percentunit", decimals=1, thresholds=[(None, "green"), (0.7, "orange"), (0.9, "red")]),
        panel("stat", "Memory used", [target(f'1 - sum(node_memory_MemAvailable_bytes{{{inst}}}) / sum(node_memory_MemTotal_bytes{{{inst}}})')],
              9, 1, 5, 4, unit="percentunit", decimals=1, thresholds=[(None, "green"), (0.75, "orange"), (0.9, "red")]),
        panel("stat", "Fullest filesystem", [target(
            f'max(1 - node_filesystem_avail_bytes{{{fs}, {inst}}} / node_filesystem_size_bytes{{{fs}, {inst}}})')],
            14, 1, 5, 4, unit="percentunit", decimals=1, thresholds=[(None, "green"), (0.8, "orange"), (0.9, "red")],
            desc="Alert DiskSpaceLow fires when free space < 10%"),
        panel("stat", "Pod restarts (1h)", [target('sum(increase(kube_pod_container_status_restarts_total[1h]))')],
              19, 1, 5, 4, decimals=0, thresholds=[(None, "green"), (1, "orange"), (4, "red")]),
        panel("timeseries", "CPU utilisation by node",
              [target(f'1 - avg by (instance) (rate(node_cpu_seconds_total{{mode="idle", {inst}}}[5m]))', "{{instance}}")],
              0, 5, 12, 8, unit="percentunit", min_=0, max_=1),
        panel("timeseries", "Memory utilisation by node",
              [target(f'1 - node_memory_MemAvailable_bytes{{{inst}}} / node_memory_MemTotal_bytes{{{inst}}}', "{{instance}}")],
              12, 5, 12, 8, unit="percentunit", min_=0, max_=1),
        panel("timeseries", "Disk used by mountpoint",
              [target(f'1 - node_filesystem_avail_bytes{{{fs}, {inst}}} / node_filesystem_size_bytes{{{fs}, {inst}}}',
                      "{{instance}} {{mountpoint}}")],
              0, 13, 12, 8, unit="percentunit", min_=0, max_=1,
              thresholds=[(None, "transparent"), (0.9, "red")]),
        panel("timeseries", "Disk I/O",
              [target(f'sum by (instance) (rate(node_disk_read_bytes_total{{{inst}}}[5m]))', "read {{instance}}", ref="A"),
               target(f'-sum by (instance) (rate(node_disk_written_bytes_total{{{inst}}}[5m]))', "write {{instance}}", ref="B")],
              12, 13, 12, 8, unit="Bps", desc="Writes shown as negative"),
        panel("timeseries", "Network throughput",
              [target(f'sum by (instance) (rate(node_network_receive_bytes_total{{device!~"lo|veth.*|cni.*|flannel.*|cali.*", {inst}}}[5m]))', "rx {{instance}}", ref="A"),
               target(f'-sum by (instance) (rate(node_network_transmit_bytes_total{{device!~"lo|veth.*|cni.*|flannel.*|cali.*", {inst}}}[5m]))', "tx {{instance}}", ref="B")],
              0, 21, 12, 8, unit="Bps", desc="Transmit shown as negative"),
        panel("timeseries", "Load average (1m) vs cores",
              [target(f'node_load1{{{inst}}}', "load1 {{instance}}", ref="A"),
               target(f'count by (instance) (node_cpu_seconds_total{{mode="idle", {inst}}})', "cores {{instance}}", ref="B")],
              12, 21, 12, 8),
    ]
    p.append(row("Workloads", 29))
    p += [
        panel("timeseries", "CPU by namespace",
              [target('sum by (namespace) (rate(container_cpu_usage_seconds_total{container!=""}[5m]))', "{{namespace}}")],
              0, 30, 12, 8, unit="short", desc="CPU cores used"),
        panel("timeseries", "Memory (working set) by namespace",
              [target('sum by (namespace) (container_memory_working_set_bytes{container!=""})', "{{namespace}}")],
              12, 30, 12, 8, unit="bytes"),
        panel("table", "Containers restarting (last 1h)",
              [target('sort_desc(increase(kube_pod_container_status_restarts_total[1h]) > 0)', format="table", instant=True)],
              0, 38, 24, 7, decimals=0),
    ]
    tmpl = [prom_var("instance", "label_values(node_uname_info, instance)", "Node")]
    return dashboard("shop-infrastructure", "Shop / Infrastructure (nodes + workloads)", p, templating=tmpl,
                     tags=["shop", "infrastructure"], desc="Node CPU, memory, disk, network and per-namespace usage")


# ======================================================================= 3. Logs
def logs():
    global _id
    _id = 0
    sel = '{namespace="shop", service=~"$service"}'
    p = [
        panel("stat", "Error logs (15m)", [target(f'sum(count_over_time({{namespace="shop", service=~"$service", level="error"}}[15m]))', ds=LOKI)],
              0, 0, 6, 4, ds=LOKI, decimals=0, thresholds=[(None, "green"), (1, "orange"), (50, "red")]),
        panel("stat", "Warnings (15m)", [target(f'sum(count_over_time({{namespace="shop", service=~"$service", level="warning"}}[15m]))', ds=LOKI)],
              6, 0, 6, 4, ds=LOKI, decimals=0, thresholds=[(None, "green"), (10, "orange")]),
        panel("stat", "Log lines / s", [target(f'sum(rate({sel}[5m]))', ds=LOKI)],
              12, 0, 6, 4, ds=LOKI, decimals=1, unit="short", thresholds=[(None, "blue")]),
        panel("stat", "Error share of logs", [target(
            f'sum(rate({{namespace="shop", service=~"$service", level="error"}}[5m])) / sum(rate({sel}[5m]))', ds=LOKI)],
            18, 0, 6, 4, ds=LOKI, unit="percentunit", decimals=2, thresholds=[(None, "green"), (0.01, "orange"), (0.05, "red")]),
        panel("timeseries", "Log volume by service",
              [target(f'sum by (service) (count_over_time({sel}[1m]))', "{{service}}", ds=LOKI)],
              0, 4, 12, 8, ds=LOKI, options={"legend": {"displayMode": "list", "placement": "bottom"}}),
        panel("timeseries", "Error count by service",
              [target(f'sum by (service) (count_over_time({{namespace="shop", service=~"$service", level="error"}}[1m]))', "{{service}}", ds=LOKI)],
              12, 4, 12, 8, ds=LOKI),
        panel("table", "Top error messages (15m)",
              [target('topk(10, sum by (service, msg) (count_over_time({namespace="shop", level="error"} | json [15m])))',
                      ds=LOKI, queryType="instant")],
              0, 12, 10, 9, ds=LOKI, decimals=0),
        panel("logs", "Recent errors and warnings (click trace_id -> Tempo)",
              [target(f'{{namespace="shop", service=~"$service", level=~"error|warning"}} |= "$search"', ds=LOKI)],
              10, 12, 14, 9, ds=LOKI,
              options={"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending", "enableLogDetails": True,
                       "prettifyLogMessage": False, "dedupStrategy": "none"}),
        panel("logs", "All shop logs (filter with the Search box)",
              [target(f'{sel} |= "$search"', ds=LOKI)],
              0, 21, 24, 10, ds=LOKI,
              options={"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending", "enableLogDetails": True}),
    ]
    tmpl = [
        {"name": "service", "label": "Service", "type": "custom", "query": "frontend,orders,payments,loadgen",
         "includeAll": True, "multi": True, "allValue": ".*",
         "current": {"selected": True, "text": "All", "value": "$__all"},
         "options": []},
        {"name": "search", "label": "Search", "type": "textbox", "query": "", "current": {"text": "", "value": ""}},
    ]
    return dashboard("shop-logs", "Shop / Application logs", p, templating=tmpl,
                     tags=["shop", "logs"], desc="Error count, log volume and recent errors from Loki")


# ======================================================================== 4. SLO
def slo():
    global _id
    _id = 0
    objective = 0.995
    budget = 1 - objective
    err30 = 'sum by (service) (increase(http_requests_total{namespace="shop", status=~"5.."}[30d]))'
    tot30 = 'sum by (service) (increase(http_requests_total{namespace="shop"}[30d]))'
    p = [
        panel("stat", "Availability (30d) vs 99.5% objective", [target(f'1 - ({err30} / {tot30})', "{{service}}")],
              0, 0, 12, 5, unit="percentunit", decimals=3,
              thresholds=[(None, "red"), (objective, "green")]),
        panel("gauge", "Error budget remaining (30d)", [target(f'1 - (({err30} / {tot30}) / {budget})', "{{service}}")],
              12, 0, 12, 5, unit="percentunit", min_=0, max_=1, decimals=1,
              thresholds=[(None, "red"), (0.25, "orange"), (0.5, "green")]),
        panel("timeseries", "Burn rate (1h window) - page above 14.4x",
              [target(f'slo:sli_error:ratio_rate1h / {budget}', "{{service}}")],
              0, 5, 12, 8, thresholds=[(None, "transparent"), (14.4, "red")],
              desc="1x = consuming budget exactly at the allowed pace"),
        panel("timeseries", "Burn rate (6h window) - ticket above 6x",
              [target(f'slo:sli_error:ratio_rate6h / {budget}', "{{service}}")],
              12, 5, 12, 8, thresholds=[(None, "transparent"), (6, "orange")]),
        panel("timeseries", "SLI: successful request ratio (5m)",
              [target('1 - slo:sli_error:ratio_rate5m', "{{service}}")],
              0, 13, 24, 8, unit="percentunit", max_=1,
              thresholds=[(None, "red"), (objective, "transparent")]),
    ]
    return dashboard("shop-slo", "Shop / SLO: availability 99.5%", p, tags=["shop", "slo"],
                     desc="Error budget and multi-window burn rates (Google SRE workbook)", time_from="now-6h")


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for name, fn in [("service-overview", service_overview), ("infrastructure", infrastructure),
                     ("application-logs", logs), ("slo", slo)]:
        path = OUT / f"{name}.json"
        path.write_text(json.dumps(fn(), indent=2) + "\n")
        print(f"wrote {path.relative_to(OUT.parent)} ({len(fn()['panels'])} panels)")
