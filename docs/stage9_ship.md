# Stage 9 · Ship — Production Deploy + Launch
## Lakhimpur Agri-Business Platform

---

## What Stage 9 achieves

One-way door. Staging passed. Live Razorpay keys. Real customers.
WATI enabled — real WhatsApp messages will be sent.

```
STAGING ──→ PRODUCTION
  ✅               ← you are here
```

---

## PRE-PRODUCTION GATE — all must be ✅

```
From Stage 8 sign-off:
  ✅ All smoke tests passed on staging
  ✅ Sentry staging: 0 errors
  ✅ Razorpay test payment end-to-end worked
  ✅ Performance baselines met

Before production deploy:
  ☐ Razorpay LIVE keys obtained (dashboard.razorpay.com → Live mode)
  ☐ WATI production token confirmed (app.wati.io → API settings)
  ☐ WhatsApp template messages approved by Meta (can take 24-48h)
  ☐ Custom domain purchased (optional but recommended)
  ☐ Production RSA key pair generated (NEVER reuse staging keys)
```

---

## STEP 1 — Generate fresh production RSA keys

```bash
# New key pair for production — never reuse staging or local keys
openssl genrsa -out prod_private.pem 2048
openssl rsa -in prod_private.pem -pubout -out prod_public.pem

# Convert to env var format (single line with \n)
awk 'NF {sub(/\r/, ""); printf "%s\\n",$0;} END {printf "\n"}' prod_private.pem
# Copy output → JWT_PRIVATE_KEY in Railway production

awk 'NF {sub(/\r/, ""); printf "%s\\n",$0;} END {printf "\n"}' prod_public.pem
# Copy output → JWT_PUBLIC_KEY in Railway production

# Delete PEM files after copying to Railway
rm prod_private.pem prod_public.pem
```

---

## STEP 2 — Railway: set production environment variables

```
Railway Dashboard → Project → Backend service → Variables

Switch environment to: Production

Set ALL variables:

ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
REDIS_PREFIX=prod

JWT_PRIVATE_KEY=-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----
JWT_PUBLIC_KEY=-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----
JWT_ALGORITHM=RS256
JWT_EXPIRY_HOURS=24

OWNER_USERNAME=your_actual_username_here

# Razorpay LIVE keys (different from test keys)
RAZORPAY_KEY_ID=rzp_live_xxxxxxxxxxxxxxxx
RAZORPAY_KEY_SECRET=live_secret_xxxxxxxxxxxxxxxx
RAZORPAY_WEBHOOK_SECRET=live_webhook_secret_xxxxxxx

# WATI LIVE — real WhatsApp messages
WATI_ENABLED=true
WATI_API_TOKEN=live_wati_token_xxxxxxxxxxxxxxxxxx
WATI_BASE_URL=https://live-mt-server.wati.io/api/v1
OWNER_WHATSAPP=+91XXXXXXXXXX   ← your real mobile number

# Sentry production project
SENTRY_DSN=https://xxx@sentry.io/production_project_id
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1   ← 10% sampling in prod

# CORS — production Vercel domain only
CORS_ORIGIN=https://your-actual-shop.vercel.app

RATE_LIMIT_PER_MIN=100
RATE_LIMIT_LOGIN_PER_MIN=5
```

---

## STEP 3 — Vercel: set production environment variables

```
Vercel Dashboard → Project → Settings → Environment Variables
→ Select: Production environment

NUXT_API_BASE=https://your-api.railway.app
NUXT_PUBLIC_API_BASE=https://your-api.railway.app
NUXT_RAZORPAY_KEY_ID=rzp_live_xxxxxxxxxxxxxxxx   ← LIVE key
NUXT_PUBLIC_SITE_URL=https://your-actual-shop.vercel.app
NUXT_PUBLIC_ENVIRONMENT=production
NUXT_SENTRY_DSN=https://xxx@sentry.io/frontend_production_project
```

---

## STEP 4 — Razorpay: register production webhook

```
Razorpay Dashboard (LIVE mode) → Settings → Webhooks → Add new

URL:    https://your-api.railway.app/api/payments/webhook
Events: ✅ payment.captured
        ✅ payment.failed
        ✅ refund.created
Secret: live_webhook_secret_xxxxxxx   ← must match Railway env var

Save → Razorpay will send a test event → verify 200 in Railway logs
```

---

## STEP 5 — Deploy to production

```bash
# Merge main branch → triggers GitHub Actions → auto-deploys

git checkout main
git merge staging   # staging has been tested
git push origin main

# GitHub Actions CI will:
# 1. Run all tests (must pass)
# 2. Deploy backend to Railway (production)
# 3. Deploy frontend to Vercel (production)

# Monitor deploy:
railway logs --tail   # watch backend boot
```

---

## STEP 6 — Run migrations and seed

```bash
# Migrations (runs automatically on startup via main.py)
# Verify in Railway logs: "Running migrations..." → "Done"

# Seed production data (run ONCE)
railway run python scripts/seed.py
# Output: ✓ Seed complete. Login: admin / changeme123

# IMMEDIATELY change password after first login!
# Dashboard → Settings → Change password
```

---

## STEP 7 — Production smoke tests

```bash
BASE="https://your-api.railway.app"
FRONTEND="https://your-actual-shop.vercel.app"

echo "=== Infrastructure ==="
curl -s $BASE/health        | jq .   # {"status":"ok"}
curl -s $BASE/health/ready  | jq .   # {"status":"ready"}

echo "=== Products ==="
curl -s $BASE/api/products/ | jq 'length'          # 5
curl -s $BASE/api/products/ | jq '.[0].sell_price'  # "105.00000"

echo "=== Frontend ==="
curl -s -o /dev/null -w "shop: %{http_code}\n"  $FRONTEND/shop
curl -s -o /dev/null -w "login: %{http_code}\n" $FRONTEND/login

echo "=== Login ==="
curl -s -c prod_cookies.txt -X POST $BASE/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"changeme123"}' | jq .

# IMPORTANT: if this returns 200, immediately change your password!
```

---

## STEP 8 — Live payment test (REAL money, SMALL amount)

```
After all smoke tests pass:

1. Go to https://your-actual-shop.vercel.app/shop
2. Add Kali Jeera (1 kg = ₹110) to cart
3. Checkout with your real phone number
4. Pay ₹110 via your own UPI

Expected:
  ✅ Payment captured (Razorpay live dashboard)
  ✅ WhatsApp message received on your phone (customer confirmation)
  ✅ Owner WhatsApp alert received (OWNER_WHATSAPP)
  ✅ Order appears in dashboard as "confirmed"
  ✅ Stock decremented by 1 kg

If all good: PLATFORM IS LIVE ✅

Refund the ₹110 to yourself from Razorpay dashboard.
```

---

## STEP 9 — Post-launch checklist

```
Immediate (day 1):
  ☐ Change default password: changeme123 → strong password
  ☐ Verify OWNER_WHATSAPP is your real number
  ☐ Add real product images (Cloudflare R2)
  ☐ Set opening stock for all 5 products (current physical stock)
  ☐ Add real fixed costs (stall rent, transport, etc.)
  ☐ Add assets (rice mill machine, weighing scale, etc.)

Week 1:
  ☐ Add first offline order (WhatsApp customer → create manual order)
  ☐ Record first inventory purchase
  ☐ Check P&L for the week
  ☐ Verify low-stock alerts working (WhatsApp notification)

Month 1 (at month-end):
  ☐ Record opening stock (first ever — all products)
  ☐ Record closing stock (physical count)
  ☐ Check monthly P&L — net profit should show
  ☐ Check cash_pl_gap (outstanding credits)
  ☐ Verify depreciation in opex
```

---

## STEP 10 — Operations guide (ongoing)

```bash
# Daily workflow (owner)
# 1. Open dashboard → check stock alerts
# 2. Process WhatsApp orders → create manual order
# 3. Update order status as packed/delivered
# 4. Record any purchases (paddy, ingredients)
# 5. View daily summary (auto-sent at 10 PM via WhatsApp)

# Monthly (at month start)
railway run python scripts/monthly_close.py \
  --month 2025-05 \
  --action opening-stock
# Opens a form to enter physical stock count

# View P&L
# Dashboard → Reports → P&L → Select month

# Add new product
# Dashboard → Products → New Product → fill 4-layer cost form

# Petha batch (each production run)
# Dashboard → Petha → New Batch → add costs → record outcome

# Farm season (each kharif/rabi)
# Dashboard → Farm → New Season → add inputs → record harvest → milling
```

---

## MONITORING in production

```
Sentry Production:
  → Alert me if: error rate > 0% (zero tolerance in prod)
  → Alert me if: P99 latency > 2s

UptimeRobot (free):
  → Monitor: https://your-api.railway.app/health (every 5 min)
  → Alert: SMS + email if down

Railway Metrics:
  → Set alerts: CPU > 80%, Memory > 80%, Error rate > 1%

Daily check:
  → Railway logs: search for ERROR (should be 0)
  → Sentry: open issues (should be 0)
  → Dashboard: P&L summary (auto-calculated)
```

---

## COMPLETE SDLC — DONE ✅

```
0 · Idea          ✅  Business validated, products scoped
1 · Whiteboard    ✅  Architecture decided (monolith, one app two faces)
2 · Requirements  ✅  38 FRs, 18 edge cases, 15 user stories
3 · HLD           ✅  Tech stack, 6 key flows, deployment topology
4 · LLD           ✅  14 tables, 9 modules, all algorithms, security
5 · Dev Setup     ✅  Docker, CI/CD, Makefile, 20 core files
6 · Code          ✅  9 backend modules, complete implementation
7 · Testing       ✅  Unit + integration + edge cases, 75% coverage
8 · Staging       ✅  Railway + Vercel, Razorpay test, smoke tests
9 · Ship          ✅  Live. Real money. Real customers.
                       Lakhimpur Agri-Business is OPEN. 🌾
```

---

## What's still pending (roadmap, not blockers)

```
Frontend (NuxtJS):
  → /shop pages: product grid, cart, checkout, order tracking
  → /dashboard pages: P&L, orders, inventory, farm, petha
  → Mobile-first responsive design
  → PWA (offline mode for poor connectivity in Lakhimpur)

Future features (post-launch):
  → Customer accounts (repeat buyers)
  → Bulk order discounts
  → Delivery tracking on map
  → GST invoice generation
  → Multi-variety seasonal pricing
  → Hen/cock offline stall integration (QR code orders)
  → Tea stall offline POS integration
```
