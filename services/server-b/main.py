import os
import time
import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
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

# ── Resource ──────────────────────────────────────────────────────────────────
resource = Resource(attributes={SERVICE_NAME: "server-b"})

# ── Metrics ───────────────────────────────────────────────────────────────────
prom_reader = PrometheusMetricReader()
meter_provider = MeterProvider(resource=resource, metric_readers=[prom_reader])
metrics.set_meter_provider(meter_provider)

meter = metrics.get_meter("server-b")
http_requests = meter.create_counter("http_requests",               description="Total HTTP requests")
http_duration = meter.create_histogram("http_request_duration_seconds", description="HTTP request duration in seconds")
db_queries    = meter.create_counter("db_queries",                  description="Total database queries")
db_duration   = meter.create_histogram("db_query_duration_seconds", description="Database query duration in seconds")

# ── Traces ────────────────────────────────────────────────────────────────────
OTLP_ENDPOINT = os.getenv("OTLP_ENDPOINT", "http://tempo:4318/v1/traces")
tracer_provider = TracerProvider(resource=resource)
tracer_provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint=OTLP_ENDPOINT))
)
trace.set_tracer_provider(tracer_provider)
tracer = trace.get_tracer("server-b")

# ── DB config ─────────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "postgres"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "dbname":   os.getenv("DB_NAME", "labdb"),
    "user":     os.getenv("DB_USER", "labuser"),
    "password": os.getenv("DB_PASS", "labpass123"),
}


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Server B", description="Data Layer — queries PostgreSQL")

FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider, excluded_urls="metrics,health")

SKIP_PATHS = {"/metrics", "/health"}


@app.middleware("http")
async def record_http_metrics(request: Request, call_next):
    if request.url.path in SKIP_PATHS:
        return await call_next(request)
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    http_requests.add(1, {"method": request.method, "route": request.url.path, "status_code": str(response.status_code)})
    http_duration.record(duration, {"method": request.method, "route": request.url.path})
    return response


@app.get("/metrics", include_in_schema=False)
async def prometheus_metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "server-b"}


class OrderIn(BaseModel):
    user_id: int
    product: str
    amount: float
    status: str = "pending"


# ── Helper: 執行 DB query 並記錄 span + metrics ──────────────────────────────
def _query(sql: str, params=None, operation="SELECT", table="?"):
    with tracer.start_as_current_span(
        f"db {operation} {table}",
        attributes={
            "db.system": "postgresql",
            "db.operation": operation,
            "db.sql.table": table,
            "db.statement": sql.strip(),
        },
    ):
        start = time.perf_counter()
        status = "success"
        try:
            conn = get_conn()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql, params)
            if operation == "INSERT":
                result = cur.fetchone()
                conn.commit()
            else:
                result = cur.fetchall()
            cur.close()
            conn.close()
            return result
        except Exception as exc:
            status = "error"
            span = trace.get_current_span()
            span.record_exception(exc)
            raise
        finally:
            dur = time.perf_counter() - start
            db_queries.add(1, {"operation": operation, "table": table, "status": status})
            db_duration.record(dur, {"operation": operation, "table": table})


# ── Internal API (called by Server A) ────────────────────────────────────────
@app.get("/internal/users")
async def get_users():
    try:
        rows = _query(
            "SELECT id, username, email, region, created_at FROM users ORDER BY created_at DESC LIMIT 50",
            operation="SELECT", table="users"
        )
        return {"users": [dict(r) for r in rows], "count": len(rows)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/internal/orders")
async def get_orders():
    try:
        rows = _query(
            "SELECT id, user_id, product, amount, status, created_at FROM orders ORDER BY created_at DESC LIMIT 50",
            operation="SELECT", table="orders"
        )
        return {"orders": [dict(r) for r in rows], "count": len(rows)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/internal/orders")
async def create_order(order: OrderIn):
    try:
        row = _query(
            "INSERT INTO orders (user_id, product, amount, status) VALUES (%s, %s, %s, %s) RETURNING id",
            (order.user_id, order.product, order.amount, order.status),
            operation="INSERT", table="orders"
        )
        return {"id": dict(row)["id"], "status": "created"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
