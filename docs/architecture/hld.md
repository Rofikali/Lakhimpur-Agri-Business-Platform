# High Level Design (HLD)

## Architecture decision: one app, two faces

A single FastAPI backend serves both the public shop and the owner dashboard.
A single NuxtJS frontend renders both `/shop` (SSR, public) and `/dashboard`
(SSR + client hydration, auth-gated).

**Why not microservices?**
Single developer. Single district. 10–30 orders/day. Microservices would add
deployment complexity with zero benefit at this scale. The module boundaries
are clean enough to split later if needed.

---

## System diagram

```
                        ┌─────────────────────────────────┐
                        │          NuxtJS Frontend         │
                        │                                   │
                        │  /shop/*          /dashboard/*   │
                        │  (SSR, public)    (SSR, owner)   │
                        └──────────┬────────────────────────┘
                                   │ HTTP/JSON
                                   ▼
                        ┌─────────────────────────────────┐
                        │         FastAPI Backend          │
                        │                                   │
                        │  /api/auth        /api/orders    │
                        │  /api/products    /api/payments  │
                        │  /api/inventory   /api/pl        │
                        │  /api/farm        /api/petha     │
                        │  /api/notify      /api/finance   │
                        └──┬──────────┬──────────┬─────────┘
                           │          │          │
                     ┌─────┘    ┌─────┘    ┌─────┘
                     ▼          ▼          ▼
              ┌──────────┐ ┌─────────┐ ┌─────────┐
              │PostgreSQL│ │  Redis  │ │External │
              │    15    │ │    7    │ │Services │
              │NUMERIC   │ │cache +  │ │Razorpay │
              │(15,5)    │ │sessions │ │WATI     │
              └──────────┘ └─────────┘ └─────────┘
```

---

## Technology stack

| Layer | Choice | Version | Rationale |
|---|---|---|---|
| Language | Python | 3.12 | Async support, Decimal arithmetic, ecosystem |
| Web framework | FastAPI | 0.111+ | Async-first, Pydantic v2 built-in, OpenAPI auto-docs |
| ORM | SQLAlchemy | 2.0+ | Async sessions, typed Mapped columns, migrations via Alembic |
| DB driver | asyncpg | 0.29+ | Native async PostgreSQL — 3-5× faster than psycopg2 |
| Database | PostgreSQL | 15+ | NUMERIC(15,5) for money, JSONB, generated columns, row locking |
| Cache / sessions | Redis | 7+ | JWT blocklist, P&L cache, rate limits, alert throttle |
| Frontend | NuxtJS | 3.x | SSR for SEO on /shop, SPA for /dashboard, Vue 3 |
| State management | Pinia | 2.x | Vue-native, TypeScript-friendly |
| Package manager | uv | latest | 10-100× faster than pip, lockfile, workspace support |
| Payments | Razorpay | API v1 | UPI + cards, webhooks, INR native |
| WhatsApp | WATI | API v1 | WhatsApp Business template messages |
| Monitoring | Sentry | 2.x | Error tracking + performance |
| Tracing | OpenTelemetry | 1.24+ | Distributed traces across DB + Redis + HTTP |
| Deployment | Railway (BE) + Vercel (FE) | — | Git-push deploy, auto-scale, managed PG + Redis |

---

## Six critical flows

### 1. Online order + payment

```
Customer → /shop/checkout
  → POST /api/orders (idempotency_key, items, razorpay)
  → Validate stock (no lock yet, just check)
  → INSERT order (status=pending)
  → Razorpay createOrder(amount_paise)
  → Return {order_id, razorpay_order_id} to frontend
  → Customer pays via UPI on Razorpay
  → Razorpay → POST /api/payments/webhook
  → Verify HMAC-SHA256 signature
  → Check idempotency (Redis 7-day TTL)
  → BEGIN; confirm order + SELECT FOR UPDATE + decrement stock; COMMIT
  → BackgroundTask: notify customer + notify owner (WATI)
  → Return 200 OK to Razorpay
```

### 2. P&L calculation

```
Owner → GET /api/pl/monthly?month=2025-05
  → Check Redis cache (past months only)
  → Cache HIT  → return immediately (< 100ms)
  → Cache MISS → fetch all entries for month (single CTE query)
  → Python Decimal arithmetic (never float)
  → COGS = opening + own_prod + purchased + normal_loss + consumed − closing
  → net_profit = gross_profit − abnormal_loss − opex_total
  → Cache result (past months only, 24h TTL)
  → Return all values as strings (5 decimal places)
```

### 3. Farm milling → inventory

```
Owner → POST /api/farm/seasons/{id}/milling
  → Record milling details (dhan_sent, chawl_received, byproducts)
  → Calculate yield%: chawl / dhan × 100
  → Calculate byproduct revenue: husk×price + bran×price + broken×price
  → Calculate cost_per_kg_chawl: (cultivation_cost + milling_charges − byproduct) / chawl_kg
  → Transfer price: cost_per_kg_chawl × 1.12 (12% inter-segment markup)
  → POST to /api/inventory/entries (type=production, unit_cost=cost_per_kg_chawl)
  → UPDATE inventory_stock (current_qty += chawl_received_kg)
  → Season status → milled
```

### 4. Petha batch → inventory

```
Owner → POST /api/petha/batches (with costs)
  → Record ingredient + labor + fuel costs
  → total_batch_cost = SUM(all cost lines)
  → expiry_date = batch_date + shelf_life_days
  → PATCH /api/petha/batches/{id}/outcome (good_pieces, rejected_pieces)
  → cost_per_piece = total_batch_cost / good_pieces  ← absorption costing
  → Rejected pieces' cost absorbed by good pieces (NOT a P&L loss)
  → POST to /api/inventory/entries (type=production, unit_cost=cost_per_piece)
  → Batch status → completed
  → On expiry with unsold: wastage_abnormal entry → P&L abnormal loss
```

### 5. Auth (JWT RS256)

```
Owner → POST /api/auth/login {username, password}
  → SELECT owner WHERE username = ?
  → bcrypt.verify(password, hash) — constant time
  → create_access_token(owner_id)  ← RS256, 24h expiry, jti UUID
  → Set-Cookie: token=JWT; HttpOnly; Secure; SameSite=Strict
  → Return {owner_id, username, expires_at}

Protected route:
  → Read cookie → decode JWT (RS256 public key)
  → Check Redis blocklist (jti key)
  → Return 401 if invalid/expired/blocklisted

Logout:
  → Add jti to Redis blocklist (TTL = remaining token lifetime)
  → Clear cookie (Max-Age=0)
```

### 6. Stock update + low-stock alert

```
(After order confirmed or stock entry posted)
  → UPDATE inventory_stock SET current_qty -= qty (row-locked)
  → INCR Redis version key (invalidates product cache)
  → IF current_qty < low_stock_threshold:
      → Check Redis throttle key (12h TTL, SET IF NOT EXISTS)
      → IF no throttle key: send WATI alert to owner
      → SET throttle key (prevents alert spam)
```

---

## Deployment topology

```
GitHub (main branch)
        │
        ├── GitHub Actions CI
        │     ├── run tests (PostgreSQL + Redis services)
        │     ├── ruff + black lint
        │     └── coverage ≥ 75%
        │
        ├── Railway (backend)
        │     ├── FastAPI service (2 workers)
        │     ├── PostgreSQL 15 (managed)
        │     └── Redis 7 (managed)
        │
        └── Vercel (frontend)
              └── NuxtJS SSR
                    ├── /shop/* — CDN cached (5-10 min)
                    └── /dashboard/* — no cache, auth-gated
```

---

## External integrations

| Service | Purpose | Failure mode |
|---|---|---|
| Razorpay | UPI payment processing, webhook on capture | Order stays pending. Owner marks paid manually. |
| WATI | WhatsApp Business notifications | Fire-and-forget. Failure logged, never blocks order. |
| Cloudflare R2 | Product image storage | Images show placeholder. Orders still work. |
| Sentry | Error tracking + performance | Monitoring only. No business logic dependency. |
| OpenTelemetry | Distributed tracing | Monitoring only. |

---

## Non-functional requirements

| Requirement | Target | How |
|---|---|---|
| Money precision | ₹0.00001 (5 dp) | NUMERIC(15,5) in DB, Python Decimal everywhere, string in JSON |
| Response time | < 500ms p95 | Redis caching, eager loading, async DB |
| Availability | 99.9% | Railway auto-restart, health checks, UptimeRobot |
| Security | OWASP Top 10 | JWT RS256, HMAC webhooks, rate limiting, input validation |
| Audit trail | 7 years | Soft delete only, immutable financial entries |
| Mobile-first | /shop | NuxtJS responsive, Razorpay mobile SDK |