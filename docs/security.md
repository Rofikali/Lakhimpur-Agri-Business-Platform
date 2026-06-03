# Security

## Current backend security status

Verified in GitHub Codespaces on 2026-06-03:

| Control | Status | Evidence |
|---|---|---|
| Owner login | Working | `POST /api/auth/login` accepts seeded owner and sets HttpOnly JWT cookie |
| JWT signing | Working | RS256 private/public key configuration is loaded from backend env |
| Logout invalidation | Implemented | JWT `jti` is stored in Redis blocklist on logout |
| Public catalog access | Working | `GET /api/products/` is public through `optional_owner` |
| Owner endpoints | Implemented | Mutating product/payment routes use `require_owner` |
| Razorpay webhook signature | Implemented | Webhook verifies HMAC before processing |
| Webhook idempotency | Implemented | Redis key `webhook:rzp:{payment_id}` with 7-day TTL |
| Float rejection | Tested | Unit tests reject float input for money/quantity schemas |
| Request logging | Implemented | Structured request logs include method, path, status, duration, request ID |
| Rate limiting | Partial | Global SlowAPI limiter is configured; endpoint-specific login limits still need verification/tests |
| Frontend dashboard guard | Planned | Frontend work is pending |
| Production headers | Planned | To be enforced in Nuxt/Vercel config during frontend/deploy stages |

---

## Threat model — STRIDE

| Threat | Attack | Mitigation | Status |
|---|---|---|---|
| **S**poofing | Fake owner login | bcrypt via passlib, same error for wrong username/password | Implemented |
| **S**poofing | Fake Razorpay webhook | HMAC-SHA256 signature verification on every webhook | Implemented |
| **T**ampering | Modify order amount in transit | Pydantic validation; HTTPS required in production deployment | Partial |
| **T**ampering | Replay webhook to double-confirm | 7-day Redis idempotency key per `razorpay_payment_id` | Implemented |
| **T**ampering | Direct DB modification of financial records | Soft delete policy and reverse-entry rule documented | Partial |
| **R**epudiation | Owner denies creating entry | `created_at`, `reference_id` on stock entries | Implemented |
| **I**nfo disclosure | Customer phone in logs | Request logging does not log request bodies | Implemented |
| **I**nfo disclosure | Secrets in source code | `.env*` ignored; production secrets live in platform env vars | Implemented |
| **I**nfo disclosure | JWT token accessible to JS | `HttpOnly` cookie | Implemented |
| **D**enial of service | Flood API | SlowAPI global limiter configured | Partial |
| **D**enial of service | Brute-force login | Endpoint-specific login throttling still needs verification/tests | Planned |
| **E**levation of privilege | Customer accessing owner routes | `require_owner` dependency on owner endpoints | Implemented |
| **E**levation of privilege | Forged JWT | RS256 asymmetric signing | Implemented |

---

## OWASP Top 10 mapping

### A01 — Broken Access Control
**Risk:** Customer reaches owner dashboard or another customer's order.

**Mitigations:**
- NuxtJS server middleware on all `/dashboard/**` routes once frontend is built
- FastAPI `require_owner` dependency on every owner endpoint
- Orders accessible by UUID only — no sequential IDs to enumerate
- No wildcard CORS — only the exact Vercel domain is allowed

```python
# Every owner route:
@router.get("/", response_model=list[OrderResponse])
async def list_orders(owner: dict = Depends(require_owner), ...):
```

---

### A02 — Cryptographic Failures
**Risk:** Passwords or tokens exposed.

**Mitigations:**
- Passwords: bcrypt through passlib; `bcrypt` is pinned below 4.1 for compatibility
- JWT: RS256 asymmetric — private key never leaves Railway
- Transport: HTTPS enforced on Railway and Vercel (HSTS)
- Cookies: `HttpOnly; Secure; SameSite=Strict` — JS cannot read, HTTPS only, CSRF immune
- Secrets: environment variables only — never in code or git

---

### A03 — Injection
**Risk:** SQL injection via user input.

**Mitigations:**
- SQLAlchemy ORM exclusively — all queries use parameterised binding
- No raw `db.execute(f"SELECT ... {user_input}")` anywhere
- Pydantic validates and coerces all input before it reaches the service layer
- String length limits on all VARCHAR fields

```python
# ✅ Parameterised — safe
select(Product).where(Product.slug == slug)

# ❌ Never done
await db.execute(f"SELECT * FROM products WHERE slug = '{slug}'")
```

---

### A04 — Insecure Design
**Risk:** Race conditions, missing business logic guards.

**Mitigations:**
- `SELECT FOR UPDATE` row lock prevents oversell race condition
- Idempotency keys prevent duplicate orders and duplicate webhook processing
- Stock never goes below zero — CHECK constraint at DB level + application check
- Order status machine — invalid transitions rejected (e.g. confirmed → pending)

---

### A05 — Security Misconfiguration
**Risk:** Default credentials, open admin panels, verbose errors.

**Mitigations:**
- Swagger UI (`/docs`) disabled in production (`docs_url=None`)
- No default passwords — seed script generates placeholder, owner must change
- DEBUG=false in production
- CORS: exact origin only, `allow_credentials=True` required for cookies
- All Railway services in private network — only port 8000 exposed

---

### A06 — Vulnerable Components
**Risk:** Outdated dependencies with known CVEs.

**Mitigations:**
- All dependencies pinned in `uv.lock` — reproducible builds
- Dependabot / Renovate on GitHub repo for automated PRs
- Monthly `uv run pip-audit` in CI once CI is wired

---

### A07 — Identification and Authentication Failures
**Risk:** Session hijacking, brute force, credential stuffing.

**Mitigations:**
- JWT expiry: 24 hours
- Server-side invalidation: Redis blocklist on logout (jti key)
- Login rate limit target: 5 attempts per minute per IP; add endpoint-specific test before production
- Constant-time password comparison (bcrypt internals)
- Same error message for wrong username and wrong password (prevents enumeration)

```python
# ✅ Same error — prevents username enumeration
if not owner or not verify_password(password, owner.password_hash):
    raise InvalidCredentialsError()
```

---

### A08 — Software and Data Integrity Failures
**Risk:** Tampered webhooks, supply chain attacks.

**Mitigations:**
- Razorpay webhooks: HMAC-SHA256 verification before any processing
- `uv.lock` pins all transitive dependencies — supply chain integrity
- GitHub branch protection on `main` — no direct push, CI must pass

---

### A09 — Security Logging and Monitoring Failures
**Risk:** Attacks not detected, incidents not traceable.

**Mitigations:**
- Structured JSON logs on every HTTP request with `request_id`
- Auth event logging is planned; current logging records HTTP request metadata
- Financial event logging is planned beyond current request logs and persisted records
- Sentry captures all unhandled exceptions in real time
- HMAC failures logged as WARNING with client IP

---

### A10 — Server-Side Request Forgery (SSRF)
**Risk:** Backend fetches attacker-controlled URLs.

**Mitigations:**
- No user-controlled URLs are fetched by the backend
- Product image uploads go directly from browser to Cloudflare R2 via presigned URL
- Backend only calls fixed external URLs: Razorpay API, WATI API

---

## Authentication flow

```
POST /api/auth/login
│
├── SELECT owner WHERE username = ?          (parameterised)
├── bcrypt.checkpw(password, hash)           (constant time, ~300ms)
├── IF fail → raise InvalidCredentialsError  (same for wrong user OR wrong pass)
│
├── create JWT payload:
│   { sub: owner_id, role: "owner", iat, exp, jti: uuid4 }
├── jwt.encode(payload, PRIVATE_KEY, "RS256")
│
└── Set-Cookie: token=<JWT>; HttpOnly; Secure; SameSite=Strict; Max-Age=86400

Every protected request:
│
├── Read cookie → token
├── jwt.decode(token, PUBLIC_KEY, ["RS256"])     (verifies signature + expiry)
├── Check Redis: GET session:blocklist:{jti}     (logout check)
└── Attach payload to request.state.owner
```

---

## Input validation layers

```
HTTP request body
      │
      ▼
Pydantic schema (layer 1)
  - Field types enforced
  - Float rejected for money fields
  - Regex patterns for phone, month, status
  - String length limits
  - Min/max values
      │
      ▼
Service layer (layer 2)
  - Business rule validation
  - Stock availability check
  - Status transition validity
  - Idempotency check
      │
      ▼
Database (layer 3 — last resort)
  - CHECK constraints (qty >= 0, sell_price >= 0)
  - UNIQUE constraints (slug, order_number, razorpay_payment_id)
  - FK constraints (referential integrity)
  - NOT NULL constraints
```

---

## Secrets management

| Secret | Where stored | Rotation |
|---|---|---|
| `JWT_PRIVATE_KEY` | Railway env vars | Yearly or on breach |
| `JWT_PUBLIC_KEY` | Railway env vars | With private key |
| `DATABASE_URL` | Railway env (auto) | On breach |
| `REDIS_URL` | Railway env (auto) | On breach |
| `RAZORPAY_KEY_SECRET` | Railway env vars | Yearly |
| `RAZORPAY_WEBHOOK_SECRET` | Railway env vars | Yearly |
| `WATI_API_TOKEN` | Railway env vars | Yearly |
| `SENTRY_DSN` | Railway + Vercel | Never (not sensitive) |

**Never:**
- Commit any secret to git
- Log any secret (even partially)
- Use the same keys across local/staging/production
- Store secrets in code comments

---

## Rate limiting implementation

```python
# slowapi + Redis sliding window counter

# Current app default: 100 req/min per IP
Limiter(key_func=lambda req: req.client.host, default_limits=[f"{settings.RATE_LIMIT_PER_MIN}/minute"])

# Production target: add route-specific login limit
# @limiter.limit(f"{settings.RATE_LIMIT_LOGIN_PER_MIN}/minute")

# Redis key: ratelimit:{action}:{ip}
# TTL: 60 seconds
# Response on exceed: 429 Too Many Requests
```

---

## Security headers (Vercel + NuxtJS)

```
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Security-Policy: script-src 'self' https://checkout.razorpay.com
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
```
