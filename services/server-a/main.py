import os
import time
import httpx
from fastapi import FastAPI, Request
from starlette.responses import Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

# ── Resource（所有 signal 共用） ──────────────────────────────────────────────
resource = Resource(attributes={SERVICE_NAME: "server-a"})

# ── Metrics: Prometheus exporter ─────────────────────────────────────────────
prom_reader = PrometheusMetricReader()
meter_provider = MeterProvider(resource=resource, metric_readers=[prom_reader])
metrics.set_meter_provider(meter_provider)

meter = metrics.get_meter("server-a")

http_requests = meter.create_counter("http_requests", description="Total HTTP requests")
http_duration = meter.create_histogram("http_request_duration_seconds", description="HTTP request duration in seconds")
upstream_calls = meter.create_counter("upstream_calls", description="Total upstream calls to server-b")
upstream_duration = meter.create_histogram("upstream_call_duration_seconds", description="Upstream call duration in seconds")

# ── Traces: OTLP → Tempo ──────────────────────────────────────────────────────
OTLP_ENDPOINT = os.getenv("OTLP_ENDPOINT", "http://tempo:4318/v1/traces")
tracer_provider = TracerProvider(resource=resource)
tracer_provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint=OTLP_ENDPOINT))
)
trace.set_tracer_provider(tracer_provider)

# ── App ───────────────────────────────────────────────────────────────────────
SERVER_B_URL = os.getenv("SERVER_B_URL", "http://server-b:8002")

app = FastAPI(title="Server A", description="API Gateway — proxies requests to Server B")

# Auto-instrument: FastAPI spans + httpx W3C trace propagation
FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider, excluded_urls="metrics,health")
HTTPXClientInstrumentor().instrument(tracer_provider=tracer_provider)

SKIP_PATHS = {"/metrics", "/health"}


@app.middleware("http")
async def record_http_metrics(request: Request, call_next):
    if request.url.path in SKIP_PATHS:
        return await call_next(request)
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    labels = {
        "method": request.method,
        "route": request.url.path,
        "status_code": str(response.status_code),
    }
    http_requests.add(1, labels)
    http_duration.record(duration, {"method": request.method, "route": request.url.path})
    return response


@app.get("/metrics", include_in_schema=False)
async def prometheus_metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "server-a"}


# ── 內部 helper：呼叫 Server B ────────────────────────────────────────────────
async def _call_b(method: str, path: str, **kwargs):
    url = f"{SERVER_B_URL}{path}"
    start = time.perf_counter()
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await getattr(client, method)(url, **kwargs)
            status = str(resp.status_code)
            data = resp.json()
        except httpx.RequestError as exc:
            status = "error"
            data = {"error": str(exc)}
    duration = time.perf_counter() - start
    upstream_calls.add(1, {"endpoint": path, "status": status})
    upstream_duration.record(duration, {"endpoint": path})
    return data


# ── Public API ────────────────────────────────────────────────────────────────
@app.get("/api/users")
async def get_users():
    return await _call_b("get", "/internal/users")


@app.get("/api/orders")
async def get_orders():
    return await _call_b("get", "/internal/orders")


@app.post("/api/orders")
async def create_order(body: dict):
    return await _call_b("post", "/internal/orders", json=body)
