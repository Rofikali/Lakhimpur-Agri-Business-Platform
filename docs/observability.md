# Observability

## Four pillars

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│   METRICS   │  │   TRACING   │  │   LOGGING   │  │   ALERTING  │
│ (Prometheus)│  │(OpenTelemetry│  │ (structlog) │  │  (Sentry +  │
│             │  │  + Sentry)  │  │    JSON)    │  │  UptimeRobot│
└─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘
```

---

## Metrics

### Auto-collected (prometheus-fastapi-instrumentator)

```
# HTTP traffic
http_requests_total{method, path, status_code}
http_request_duration_seconds{path}          # histogram: p50, p95, p99
http_request_size_bytes
http_response_size_bytes

# Python runtime
python_gc_objects_collected_total
python_info
```

### Business metrics (custom — emitted from service.py)

```python
from prometheus_client import Counter, Histogram, Gauge

# Orders
orders_created_total        = Counter("orders_created_total",
                                "Orders created", ["channel", "payment_mode"])
orders_revenue_rupees       = Counter("orders_revenue_rupees_total",
                                "Revenue in rupees", ["channel"])

# Stock
stock_qty_current           = Gauge("stock_qty_current",
                                "Current stock quantity", ["product_slug", "unit"])
stock_low_alerts_total      = Counter("stock_low_alerts_total",
                                "Low stock alerts sent", ["product_slug"])

# P&L
pl_calculation_duration     = Histogram("pl_calculation_duration_seconds",
                                "P&L calculation time")
pl_cache_hits_total         = Counter("pl_cache_hits_total", "P&L cache hits")
pl_cache_misses_total       = Counter("pl_cache_misses_total", "P&L cache misses")

# Payments
payment_webhook_total       = Counter("payment_webhook_total",
                                "Webhooks received", ["status"])  # ok/failed/duplicate
payment_razorpay_duration   = Histogram("payment_razorpay_duration_seconds",
                                "Razorpay API call duration")

# Petha
petha_rejection_pct         = Histogram("petha_rejection_pct",
                                "Batch rejection percentage", ["variety"])

# Notifications
notify_sent_total           = Counter("notify_sent_total",
                                "WhatsApp messages sent", ["template", "status"])
```

### Emitting a metric in service code

```python
# In orders/service.py after order confirmed:
orders_created_total.labels(
    channel=order.channel,
    payment_mode=order.payment.payment_mode,
).inc()

orders_revenue_rupees.labels(channel=order.channel).inc(
    float(order.final_amount)  # float OK for metrics — not financial calculation
)
```

### Metrics endpoint

```
GET /metrics   → Prometheus scrape endpoint (disabled in production via env flag)
```

---

## Distributed tracing

### OpenTelemetry setup

```python
# core/telemetry.py
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor

def setup_tracing(app):
    provider = TracerProvider()
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter())
    )
    trace.set_tracer_provider(provider)

    # Auto-instrument: every request, DB query, Redis call gets a span
    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument()
    RedisInstrumentor().instrument()
```

### What a trace looks like

```
POST /api/orders (45ms)
  ├── SELECT products WHERE id = ? (2ms)
  ├── SELECT inventory_stock WHERE product_id = ? (1ms)
  ├── INSERT orders (3ms)
  ├── razorpay.createOrder (38ms)          ← external API call
  └── SET prod:idem:order:uuid (0.5ms)     ← Redis

POST /api/payments/webhook (12ms)
  ├── HMAC verify (0.1ms)
  ├── GET prod:webhook:rzp:pay_xxx (0.3ms) ← idempotency check
  ├── BEGIN (0.1ms)
  │   ├── UPDATE orders SET status='confirmed' (2ms)
  │   ├── SELECT FOR UPDATE inventory_stock (1ms)
  │   └── UPDATE inventory_stock (1ms)
  └── COMMIT (3ms)
  [background] WATI send (async — not in trace)
```

### Custom spans for critical business operations

```python
tracer = trace.get_tracer(__name__)

async def create_order(self, data, bg):
    with tracer.start_as_current_span("order.create") as span:
        span.set_attribute("order.channel", data.channel)
        span.set_attribute("order.item_count", len(data.items))
        span.set_attribute("order.payment_mode", data.payment_mode)
        # ... business logic ...

async def calculate_monthly_pl(self, month):
    with tracer.start_as_current_span("pl.calculate") as span:
        span.set_attribute("pl.month", month)
        span.set_attribute("pl.from_cache", False)
        # ... calculation ...
```

### Trace ID propagation

Every HTTP response includes `X-Trace-ID` header.
All log lines for that request include the same trace ID.
When owner reports a bug, they share the `X-Request-ID` from browser DevTools.

---

## Structured logging

### Log format (JSON, every line)

```json
{
  "timestamp":   "2025-05-10T10:30:45.123456Z",
  "level":       "INFO",
  "event":       "order_confirmed",
  "request_id":  "abc123-xyz789",
  "trace_id":    "def456-uvw012",
  "module":      "orders",
  "function":    "_confirm_and_decrement",
  "data": {
    "order_id":     "uuid-here",
    "order_number": "LKP-2025-0042",
    "channel":      "online",
    "amount":       "595.00000",
    "customer":     "+91987****210"
  },
  "duration_ms": 45,
  "environment": "production"
}
```

### Log levels

| Level | When | Examples |
|---|---|---|
| `DEBUG` | Never in production | SQL queries, Redis keys, raw payloads |
| `INFO` | Normal business events | `order_created`, `payment_received`, `stock_updated`, `pl_calculated` |
| `WARNING` | Unexpected but handled | `stock_low`, `webhook_duplicate`, `petha_expiry_soon`, `cache_miss` |
| `ERROR` | Operation failed | `payment_failed`, `wati_error`, `razorpay_timeout`, `db_query_failed` |
| `CRITICAL` | System failure | `db_unreachable`, `redis_unreachable`, `unhandled_exception` |

### Mandatory log events

```python
# Auth
logger.info("login_success",   username=owner.username)
logger.warning("login_failure", username=data.username, reason="wrong_password")
logger.info("logout",          jti=jti)

# Orders
logger.info("order_created",   order_id=order.id, channel=order.channel,
                               amount=str(order.final_amount))
logger.info("order_confirmed", order_id=order.id, payment_mode=payment.mode)
logger.info("order_cancelled", order_id=order.id, reason=order.cancel_reason)

# Payments
logger.info("webhook_received",    rzp_payment_id=rzp_id, event=event)
logger.info("webhook_verified",    rzp_payment_id=rzp_id)
logger.warning("webhook_duplicate",rzp_payment_id=rzp_id)
logger.warning("webhook_invalid_hmac", ip=client_ip)

# Stock
logger.info("stock_entry_created", entry_type=entry.entry_type,
                                   product_id=str(product_id), qty=str(qty))
logger.warning("stock_low",        product=product_name,
                                   current_qty=str(qty), threshold=str(threshold))

# P&L
logger.info("pl_calculated", month=month, duration_ms=elapsed,
                             from_cache=False, warnings=result.warnings)

# Petha
logger.info("batch_expired",  batch_id=str(batch_id),
                              abnormal_loss=str(loss))

# Notifications
logger.info("whatsapp_sent",   template=template, recipient_type=rtype)
logger.error("whatsapp_failed",template=template, error=str(e))
```

### What NEVER appears in logs

```python
# ❌ Never log these
password
password_hash
JWT token value
RAZORPAY_KEY_SECRET
WATI_API_TOKEN
Full customer phone (use mask_phone() helper)
Full razorpay_signature
Any environment variable value
```

### Correlation middleware

```python
# core/middleware/correlation.py
class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = (
            request.headers.get("X-Request-ID")
            or str(uuid.uuid4())
        )
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
```

---

## Health checks

### Endpoints

```
GET /health
→ 200 {"status": "ok"}
Used by: Railway restart trigger, basic uptime monitor

GET /health/ready
→ 200 {"status": "ready"}
→ 503 {"status": "not_ready", "db": false, "redis": false}
Used by: Load balancer readiness probe before routing traffic

GET /health/live
→ 200 {"status": "alive"}
Used by: Kubernetes liveness probe (future)
```

### Implementation

```python
@app.get("/health/ready")
async def ready():
    db_ok    = await check_db()     # SELECT 1
    redis_ok = await check_redis()  # PING
    if not db_ok or not redis_ok:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "db": db_ok, "redis": redis_ok}
        )
    return {"status": "ready"}
```

---

## Alerting rules

| Alert | Condition | Channel | Response |
|---|---|---|---|
| Site down | `/health` fails 2× in 5 min | Email + SMS (UptimeRobot) | Check Railway logs, restart service |
| High error rate | Error rate > 1% per 5 min | Sentry email | Check Sentry trace, hotfix deploy |
| Slow P95 latency | P95 > 2s on any endpoint | Sentry perf alert | Check for N+1 queries, missing index |
| DB connection pool | > 80% checked out | Railway metrics email | Check for connection leaks |
| Low stock | `current_qty < threshold` | Owner WhatsApp (WATI) | Buy more stock |
| Petha expiry | Batch expires in ≤ 3 days | Owner WhatsApp (WATI) | Sell urgently or mark expired |
| Webhook failures | > 2 consecutive HMAC fails | Sentry error | Check Razorpay webhook secret |
| Redis unavailable | PING fails | Sentry critical | Rate limits/cache will degrade |
| Payment timeout | Razorpay API > 10s | Sentry error | Owner marks paid manually |

### Daily business summary (APScheduler cron)

Runs at **10:00 PM IST** every day. Sends to `OWNER_WHATSAPP`:

```
📊 Daily Summary — 10 May 2025

Orders today:    8  (5 online · 3 offline)
Revenue today:   ₹4,250.00
Best seller:     Joha Rice (5 orders, ₹1,575)

⚠ Stock alerts:  Narikal Petha → 4 pcs (below 5 threshold)
⏰ Petha expiry: Batch #12 expires in 2 days

Month so far (May 2025):
  Revenue:     ₹18,400
  Expenses:    ₹11,200
  Net profit:  ₹7,200 (39.1%)
```

---

## Log retention policy

| Log type | Where | Retention | Reason |
|---|---|---|---|
| Application logs | Railway log viewer | 30 days | Debugging window |
| Financial audit (DB) | PostgreSQL | 7 years (never delete) | GST / Income Tax |
| Error logs | Sentry | 90 days | Pattern analysis |
| Auth/access logs | Sentry | 90 days | Security investigation |
| Webhook logs | Sentry | 1 year | Razorpay dispute window |
| Notification logs | DB `notifications` table | 1 year | Dispute resolution |