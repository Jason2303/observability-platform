"""
"Shop" demo microservices: one codebase, role chosen by SERVICE_NAME.

    loadgen --> frontend /checkout --> orders /orders --> payments /pay

Each service exposes:
  * Prometheus metrics on /metrics (RED + business metrics)
  * OpenTelemetry traces via OTLP/HTTP (context propagated between services)
  * JSON logs to stdout that include trace_id/span_id (log <-> trace correlation)

Fault injection (for testing alerts), via env vars:
  FAILURE_RATE=0.3        30% of requests return HTTP 500
  EXTRA_LATENCY_MS=1500   add latency to every request
  CRASH_ON_START=true     exit immediately (CrashLoopBackOff)
"""
import json
import logging
import os
import random
import sys
import time

import requests

# Drop prometheus_client's *_created series (noise for dashboards)
os.environ.setdefault("PROMETHEUS_DISABLE_CREATED_SERIES", "True")

from flask import Flask, Response, g, jsonify, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

SERVICE = os.getenv("SERVICE_NAME", "frontend")
PORT = int(os.getenv("PORT", "8080"))
ORDERS_URL = os.getenv("ORDERS_URL", "http://orders:8080")
PAYMENTS_URL = os.getenv("PAYMENTS_URL", "http://payments:8080")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://frontend:8080")


def _float_env(name, default=0.0):
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


FAILURE_RATE = _float_env("FAILURE_RATE")
EXTRA_LATENCY_MS = _float_env("EXTRA_LATENCY_MS")


# ----------------------------------------------------------------- logging
class JsonFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname.lower(),
            "service": SERVICE,
            "msg": record.getMessage(),
        }
        try:
            from opentelemetry import trace

            ctx = trace.get_current_span().get_span_context()
            if ctx.is_valid:
                entry["trace_id"] = format(ctx.trace_id, "032x")
                entry["span_id"] = format(ctx.span_id, "016x")
        except Exception:  # tracing must never break logging
            pass
        for key in ("route", "status", "duration_ms", "order_id", "amount"):
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        return json.dumps(entry)


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
log = logging.getLogger("shop")
log.handlers = [handler]
log.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
log.propagate = False
logging.getLogger("werkzeug").setLevel(logging.WARNING)

if os.getenv("CRASH_ON_START", "false").lower() == "true":
    log.error("CRASH_ON_START=true - exiting to simulate a crash loop")
    sys.exit(1)


# ----------------------------------------------------------------- tracing
def setup_tracing(flask_app):
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        log.info("OTEL_EXPORTER_OTLP_ENDPOINT not set - tracing disabled")
        return
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.flask import FlaskInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": SERVICE,
                "service.namespace": "shop",
                "deployment.environment": os.getenv("ENVIRONMENT", "demo"),
            }
        )
    )
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces"))
    )
    trace.set_tracer_provider(provider)
    FlaskInstrumentor().instrument_app(flask_app, excluded_urls="metrics,healthz,readyz")
    RequestsInstrumentor().instrument()
    log.info("tracing enabled, exporting to %s", endpoint)


# ----------------------------------------------------------------- metrics
# No "service" label: Prometheus adds service/namespace/pod from the ServiceMonitor.
HTTP_REQUESTS = Counter(
    "http_requests_total", "HTTP requests handled", ["method", "route", "status"]
)
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 1, 1.5, 2.5, 5),
)
# Business metrics
ORDERS = Counter("shop_orders_total", "Orders processed", ["result"])
REVENUE = Counter("shop_revenue_usd_total", "Revenue from successful orders (USD)")
PAYMENT_FAILURES = Counter("shop_payment_failures_total", "Failed payments", ["reason"])
CART_VALUE = Histogram(
    "shop_cart_value_usd", "Order value (USD)", buckets=(10, 25, 50, 100, 250, 500, 1000)
)

app = Flask(__name__)
setup_tracing(app)

PRODUCTS = [
    {"sku": "kbd-01", "name": "Mechanical keyboard", "price": 89.0},
    {"sku": "mse-02", "name": "Wireless mouse", "price": 35.0},
    {"sku": "mon-03", "name": "27in monitor", "price": 279.0},
    {"sku": "hdp-04", "name": "Headphones", "price": 129.0},
]


@app.before_request
def _start():
    g.start = time.perf_counter()
    if request.path in ("/metrics", "/healthz", "/readyz"):
        return None
    if EXTRA_LATENCY_MS > 0:
        time.sleep(EXTRA_LATENCY_MS / 1000.0)
    if FAILURE_RATE > 0 and random.random() < FAILURE_RATE:
        return jsonify(error="injected failure"), 500
    return None


@app.after_request
def _record(resp):
    if request.path in ("/metrics", "/healthz", "/readyz"):
        return resp
    route = request.url_rule.rule if request.url_rule else "unmatched"
    elapsed = time.perf_counter() - g.get("start", time.perf_counter())
    HTTP_REQUESTS.labels(request.method, route, str(resp.status_code)).inc()
    HTTP_LATENCY.labels(request.method, route).observe(elapsed)
    level = logging.ERROR if resp.status_code >= 500 else logging.INFO
    log.log(
        level,
        "%s %s -> %s",
        request.method,
        route,
        resp.status_code,
        extra={"route": route, "status": resp.status_code, "duration_ms": round(elapsed * 1000, 1)},
    )
    return resp


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


@app.get("/healthz")
def healthz():
    return jsonify(status="ok")


@app.get("/readyz")
def readyz():
    return jsonify(status="ready")


# ---------------------------------------------------------------- frontend
@app.get("/products")
def products():
    return jsonify(PRODUCTS)


@app.post("/checkout")
def checkout():
    items = random.sample(PRODUCTS, k=random.randint(1, 3))
    amount = round(sum(i["price"] for i in items), 2)
    try:
        r = requests.post(f"{ORDERS_URL}/orders", json={"items": items, "amount": amount}, timeout=5)
    except requests.RequestException as exc:
        log.error("orders service unreachable: %s", exc)
        return jsonify(error="orders unavailable"), 502
    if r.status_code >= 400:
        log.error("checkout failed: orders returned %s", r.status_code)
        return jsonify(error="checkout failed"), 502 if r.status_code >= 500 else r.status_code
    return jsonify(r.json()), 201


# ------------------------------------------------------------------ orders
@app.post("/orders")
def create_order():
    body = request.get_json(silent=True) or {}
    amount = float(body.get("amount", 0))
    order_id = f"ord-{random.randint(100000, 999999)}"
    try:
        r = requests.post(f"{PAYMENTS_URL}/pay", json={"order_id": order_id, "amount": amount}, timeout=5)
    except requests.RequestException as exc:
        ORDERS.labels("failed").inc()
        log.error("payments unreachable: %s", exc, extra={"order_id": order_id})
        return jsonify(error="payments unavailable"), 502
    if r.status_code == 402:  # declined card: business outcome, not a server error
        ORDERS.labels("declined").inc()
        log.warning("payment declined", extra={"order_id": order_id, "amount": amount})
        return jsonify(error="payment declined", order_id=order_id), 402
    if r.status_code != 200:
        ORDERS.labels("failed").inc()
        log.error("payment failed for order", extra={"order_id": order_id, "amount": amount})
        return jsonify(error="payment failed", order_id=order_id), 502
    ORDERS.labels("success").inc()
    REVENUE.inc(amount)
    CART_VALUE.observe(amount)
    log.info("order created", extra={"order_id": order_id, "amount": amount})
    return jsonify(order_id=order_id, amount=amount, status="paid")


# ---------------------------------------------------------------- payments
@app.post("/pay")
def pay():
    body = request.get_json(silent=True) or {}
    time.sleep(random.uniform(0.02, 0.12))  # talk to the "bank"
    if random.random() < 0.01:  # 1% card declines = normal business failures
        PAYMENT_FAILURES.labels("card_declined").inc()
        log.warning("card declined", extra={"order_id": body.get("order_id")})
        return jsonify(error="card declined"), 402
    return jsonify(status="ok", order_id=body.get("order_id"))


# ----------------------------------------------------------------- loadgen
def run_loadgen():
    rps = _float_env("LOADGEN_RPS", 3)
    log.info("load generator started: ~%s req/s against %s", rps, FRONTEND_URL)
    while True:
        try:
            if random.random() < 0.8:
                requests.post(f"{FRONTEND_URL}/checkout", timeout=10)
            else:
                requests.get(f"{FRONTEND_URL}/products", timeout=10)
        except requests.RequestException as exc:
            log.warning("loadgen request failed: %s", exc)
        time.sleep(max(0.01, random.expovariate(rps)))


if __name__ == "__main__":
    if SERVICE == "loadgen":
        run_loadgen()
    else:
        app.run(host="0.0.0.0", port=PORT, threaded=True)
