# Stage 8 · Staging — Deploy, Verify, Sign Off
## Lakhimpur Agri-Business Platform

---

## What Stage 8 achieves

Staging = a production-identical environment running on real infrastructure
(Railway + Vercel) with TEST Razorpay keys and WATI disabled.
Every check here must pass before you touch production.

```
LOCAL (docker-compose) ──→ STAGING (Railway + Vercel) ──→ PRODUCTION
         ✅                         ← you are here                 ⬜
```

---

## PRE-STAGING CHECKLIST — must all be ✅ before deploying

```bash
# Run on local before pushing to staging branch

make test-cov       # must pass: overall ≥ 75%, pl_engine ≥ 95%
make lint           # must pass: ruff + black, zero errors
make typecheck-fe   # must pass: no TypeScript errors

# Verify migrations are clean
make migrate        # should say "Already up to date" (no pending)

# Verify seed works on clean DB
make reset-db       # wipe + remigrate + reseed
curl http://localhost:8000/health/ready  # {"status":"ready"}
```

All green? Push to `staging` branch → CI runs → auto-deploys.

---

## PART 1 — RAILWAY SETUP (Backend)

### 1.1 Create Railway project

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Create project
railway init --name lakhimpur-biz

# Link to repo
railway link
```

### 1.2 Add PostgreSQL + Redis services

```
Railway Dashboard → Project → New Service

1. Add: PostgreSQL 15
   → DATABASE_URL auto-injected as ${{Postgres.DATABASE_URL}}

2. Add: Redis 7
   → REDIS_URL auto-injected as ${{Redis.REDIS_URL}}

3. Add: GitHub repo (backend service)
   → Root directory: /backend
   → Build command: pip install -r requirements.txt
   → Start command: uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2
```

### 1.3 Set staging environment variables

```bash
# Set ALL variables from backend/.env.staging in Railway dashboard
# Settings → Variables → Raw Editor → paste:

ENVIRONMENT=staging
DEBUG=false
LOG_LEVEL=INFO
REDIS_PREFIX=staging

# JWT — generate fresh staging keys (NOT same as local, NOT same as prod)
JWT_PRIVATE_KEY=-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----
JWT_PUBLIC_KEY=-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----
JWT_ALGORITHM=RS256
JWT_EXPIRY_HOURS=24

OWNER_USERNAME=staging_admin

# Razorpay TEST keys — no real charges
RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxxxxxx
RAZORPAY_KEY_SECRET=test_secret_xxxxxxxxxxxxxxxx
RAZORPAY_WEBHOOK_SECRET=staging_webhook_secret_xxx

# WATI DISABLED — no WhatsApp messages in staging
WATI_ENABLED=false
WATI_API_TOKEN=staging_dummy

# Sentry — staging project (separate from prod)
SENTRY_DSN=https://xxx@sentry.io/staging_project_id
SENTRY_ENVIRONMENT=staging
SENTRY_TRACES_SAMPLE_RATE=1.0

# CORS — Vercel staging preview URL
CORS_ORIGIN=https://lakhimpur-staging.vercel.app

RATE_LIMIT_PER_MIN=200
RATE_LIMIT_LOGIN_PER_MIN=20
```

### 1.4 Run migrations on staging

```bash
# Option A — Railway CLI
railway run alembic upgrade head

# Option B — Railway dashboard
# Project → Backend service → Settings → Deploy hooks
# Add: alembic upgrade head (runs on each deploy)

# Option C — Auto-run on startup (already in main.py)
# main.py startup event calls run_migrations() automatically
```

### 1.5 Seed staging database

```bash
railway run python scripts/seed.py
# Output: ✓ Seed complete. Login: staging_admin / changeme123
```

---

## PART 2 — VERCEL SETUP (Frontend)

### 2.1 Create Vercel project

```bash
# Install Vercel CLI
npm install -g vercel

cd frontend
vercel init
# Framework: Nuxt.js
# Root directory: ./  (we're already in frontend/)
```

### 2.2 Set staging environment variables

```
Vercel Dashboard → Project → Settings → Environment Variables
→ Select: Preview environments

NUXT_API_BASE=https://lakhimpur-staging.railway.app
NUXT_PUBLIC_API_BASE=https://lakhimpur-staging.railway.app
NUXT_RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxxxxxx
NUXT_PUBLIC_SITE_URL=https://lakhimpur-staging.vercel.app
NUXT_PUBLIC_ENVIRONMENT=staging
NUXT_SENTRY_DSN=https://xxx@sentry.io/frontend_staging_project
```

### 2.3 Deploy frontend to staging

```bash
# Push to staging branch → Vercel auto-deploys via GitHub integration
git push origin staging

# Or manual deploy:
cd frontend
vercel --target preview
```

---

## PART 3 — RAZORPAY WEBHOOK ON STAGING

```
Razorpay Dashboard (TEST mode) → Settings → Webhooks → Add new

URL:    https://lakhimpur-staging.railway.app/api/payments/webhook
Events: payment.captured
Secret: staging_webhook_secret_xxx  ← must match RAZORPAY_WEBHOOK_SECRET

Test: Click "Test webhook" → should see 200 OK in Railway logs
```

---

## PART 4 — STAGING SMOKE TESTS

Run these manually after every staging deploy.
All must pass before moving to production.

```bash
# Set staging URL
BASE="https://lakhimpur-staging.railway.app"
FRONTEND="https://lakhimpur-staging.vercel.app"

# ── Infrastructure ─────────────────────────────────────────────────────────
echo "=== Health checks ==="
curl -s $BASE/health        | jq .   # {"status":"ok"}
curl -s $BASE/health/ready  | jq .   # {"status":"ready"}

# ── Auth ───────────────────────────────────────────────────────────────────
echo "=== Login ==="
LOGIN=$(curl -s -c cookies.txt -X POST $BASE/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"staging_admin","password":"changeme123"}')
echo $LOGIN | jq .
# must return: {"owner_id":"...","username":"staging_admin","expires_at":"..."}

# ── Products ───────────────────────────────────────────────────────────────
echo "=== Products ==="
curl -s $BASE/api/products/ | jq 'length'
# must return: 5  (5 seeded products)

curl -s $BASE/api/products/ | jq '.[0].sell_price'
# must return a string like "105.00000" — NEVER a float

# ── Inventory ──────────────────────────────────────────────────────────────
echo "=== Stock ==="
curl -s -b cookies.txt $BASE/api/inventory/stock | jq '.[0]'

# ── Create an offline order ────────────────────────────────────────────────
echo "=== Create order ==="
PRODUCT_ID=$(curl -s $BASE/api/products/ | jq -r '.[0].id')
ORDER=$(curl -s -b cookies.txt -X POST $BASE/api/orders/ \
  -H "Content-Type: application/json" \
  -d "{
    \"idempotency_key\": \"$(uuidgen)\",
    \"customer_name\": \"Staging Test\",
    \"customer_phone\": \"+919876543210\",
    \"fulfillment_type\": \"pickup\",
    \"channel\": \"offline\",
    \"payment_mode\": \"cash\",
    \"items\": [{\"product_id\": \"$PRODUCT_ID\", \"qty\": \"1\", \"source\": \"own\"}]
  }")
echo $ORDER | jq '{status, order_number}'
# must return: {"status":"confirmed","order_number":"LKP-YYYY-0001"}

# ── P&L ────────────────────────────────────────────────────────────────────
echo "=== P&L ==="
MONTH=$(date +%Y-%m)
curl -s -b cookies.txt "$BASE/api/pl/monthly?month=$MONTH" | jq '{net_profit, warnings}'

# ── Frontend ───────────────────────────────────────────────────────────────
echo "=== Frontend pages ==="
curl -s -o /dev/null -w "%{http_code}" $FRONTEND/shop       # must return 200
curl -s -o /dev/null -w "%{http_code}" $FRONTEND/login      # must return 200
echo ""

# ── All good? ──────────────────────────────────────────────────────────────
echo "=== Done. Check all returned 200 and no errors ==="
```

---

## PART 5 — RAZORPAY TEST PAYMENT ON STAGING

```
Open: https://lakhimpur-staging.vercel.app/shop

1. Add Joha Rice to cart
2. Proceed to checkout
3. Fill customer details
4. Pay with Razorpay SDK (test mode)

Test UPI:  success@razorpay
Test card: 4111 1111 1111 1111 / any future expiry / any CVV
Test OTP:  use any 4-digit number

Expected result:
  → Order confirmed
  → Stock decremented in dashboard
  → No WhatsApp (WATI disabled in staging)
  → Webhook received (visible in Railway logs)
  → Payment captured (visible in Razorpay test dashboard)
```

---

## PART 6 — PERFORMANCE BASELINE

Run these on staging before production to detect N+1 queries or slow endpoints.

```bash
BASE="https://lakhimpur-staging.railway.app"

# Install wrk or use curl timing
# Baseline: all endpoints must respond < 500ms for typical load

# Health check (must be < 50ms)
curl -s -o /dev/null -w "health: %{time_total}s\n" $BASE/health

# Product list (must be < 300ms — cached after first call)
curl -s -o /dev/null -w "products: %{time_total}s\n" $BASE/api/products/

# P&L current month (must be < 2000ms — DB query)
curl -s -b cookies.txt -o /dev/null \
  -w "pl_current: %{time_total}s\n" \
  "$BASE/api/pl/monthly?month=$(date +%Y-%m)"

# P&L past month second call (must be < 100ms — Redis cache)
curl -s -b cookies.txt -o /dev/null \
  -w "pl_cached: %{time_total}s\n" \
  "$BASE/api/pl/monthly?month=2025-01"

# If any endpoint > 2s:
#   → Check for N+1 queries (missing eager loading)
#   → Add index if needed
#   → Add cache if appropriate
```

---

## PART 7 — SENTRY VERIFICATION

```
After running smoke tests, open Sentry staging project:

Expected: 0 errors (no unhandled exceptions during smoke tests)

If errors appear:
  → Click error → view stack trace
  → Fix in code → redeploy → re-run smoke tests
  → Do NOT move to production until Sentry is clean

Check also:
  → Performance tab: verify request traces captured
  → All API calls should have trace_id in headers (X-Trace-ID)
```

---

## PART 8 — STAGING SIGN-OFF CHECKLIST

Complete this checklist. All must be ✅ before Stage 9 (Ship).

```
Infrastructure:
  ☐ Railway backend: health/ready returns 200
  ☐ Railway PostgreSQL: migrations applied, seed data present
  ☐ Railway Redis: PING responds, cache keys visible
  ☐ Vercel frontend: all pages return 200
  ☐ Razorpay webhook: registered, test delivers 200

API smoke tests:
  ☐ Login returns JWT cookie
  ☐ Products list returns 5 products as strings (not floats)
  ☐ Offline order creates + confirms + decrements stock
  ☐ Razorpay test payment: webhook received + order confirmed
  ☐ P&L returns all fields as strings
  ☐ Cancel order restores stock

Security checks:
  ☐ /dashboard/* returns 401 without cookie
  ☐ Webhook with invalid HMAC returns 400
  ☐ Float in sell_price returns 422
  ☐ CORS: only staging Vercel domain allowed
  ☐ No secrets in response headers or error messages

Performance:
  ☐ health: < 50ms
  ☐ products list: < 300ms
  ☐ P&L current month: < 2000ms
  ☐ P&L past month (cached): < 100ms
  ☐ Create order: < 500ms

Monitoring:
  ☐ Sentry staging: 0 errors after smoke tests
  ☐ Railway logs: no ERROR or CRITICAL entries
  ☐ Structured JSON logs visible in Railway log viewer

Frontend:
  ☐ /shop loads: product grid renders with correct prices
  ☐ Cart: add item, quantity updates correctly
  ☐ Checkout: form validates phone (+91XXXXXXXXXX format)
  ☐ Razorpay modal: opens on "Pay Now"
  ☐ /login: logs in, redirects to /dashboard
  ☐ /dashboard: shows P&L summary, stock alerts
  ☐ /dashboard/orders: order table loads, status update works

Data integrity:
  ☐ sell_price in API response is string "105.00000" not float 105.0
  ☐ Order number format: LKP-YYYY-NNNN
  ☐ Duplicate order (same idempotency_key): returns same order, not duplicate
```

---

## SDLC Progress after Stage 8

```
0 · Idea          ✅
1 · Whiteboard    ✅
2 · Requirements  ✅
3 · HLD           ✅
4 · LLD           ✅
5 · Dev Setup     ✅
6 · Code          ⚠️  Backend done · Frontend pending
7 · Testing       ✅  (backend tests complete)
8 · Staging       ✅  (all checks above green)
──────────────────────────────────────────────
9 · Ship          ← NEXT
```

Stage 9 (Ship) = switch Railway and Vercel to production env vars,
point LIVE Razorpay keys, enable WATI, run smoke tests one final time.
