# Architecture Decision Records (ADRs)

Every significant technical decision is recorded here with its context,
options considered, and rationale. Future engineers (including future-you)
can understand *why*, not just *what*.

---

## ADR-001 — Monolith over microservices

**Date:** 2025-05  
**Status:** Accepted

### Context
Single developer. Single district. 10–30 orders/day. 5 SKUs. One owner.

### Options considered
| Option | Pro | Con |
|---|---|---|
| Microservices | Independent scaling, team autonomy | Distributed system complexity, 0 benefit at this scale |
| Modular monolith | Simple deploy, easy debug, one DB transaction | Must extract later if scale changes |
| Serverless | No infra management | Cold starts bad for DB connections, hard to test locally |

### Decision
**Modular monolith.** Nine internal modules with strict seam rules.
Each module owns its tables. Cross-module calls go through service interfaces.
Extraction to microservices requires only changing import to HTTP call.

---

## ADR-002 — NUMERIC(15,5) for all money

**Date:** 2025-05  
**Status:** Accepted

### Context
Financial platform. Incorrect rounding in P&L is a business trust issue.

### Options considered
| Option | Precision | Issue |
|---|---|---|
| `float` (Python/JSON) | ~15 sig figs | Binary fraction rounding: 0.1 + 0.2 = 0.30000000000000004 |
| `INTEGER` (paise, store ₹ × 100) | Exact | Awkward division, ugly in P&L reports |
| `NUMERIC(15,5)` + Python Decimal | 5 decimal places | Slower than float, but exact |

### Decision
**NUMERIC(15,5)** in PostgreSQL. Python `Decimal` everywhere.
String in all JSON responses (never float). Pydantic validators reject float input.
5 decimal places: meaningful for per-kg cost calculations (₹52.30769/kg).

### Rule
```python
# Enforced by Pydantic validator on every money field:
if isinstance(v, float):
    raise ValueError("Use string or Decimal — never float")
```

---

## ADR-003 — asyncpg over psycopg2

**Date:** 2025-05  
**Status:** Accepted

### Context
FastAPI is async. Database is the primary bottleneck.

### Options
| Driver | Style | Speed |
|---|---|---|
| psycopg2 | Sync | Baseline |
| psycopg3 | Sync + async | ~2× faster |
| asyncpg | Native async | ~3-5× faster |

### Decision
**asyncpg.** Native async, no thread pool overhead, fastest PostgreSQL driver
for Python. Used via SQLAlchemy 2.0 async engine.

**Important:** DATABASE_URL must use `postgresql+asyncpg://` scheme, not
`postgresql://` (which loads psycopg2).

---

## ADR-004 — uv over pip/poetry

**Date:** 2025-05  
**Status:** Accepted

### Context
Arch Linux Codespaces. Fast iteration. Single `pyproject.toml`.

### Options
| Tool | Install speed | Lock file | Workspace |
|---|---|---|---|
| pip | slow | requirements.txt (manual) | No |
| poetry | medium | poetry.lock | Limited |
| uv | 10-100× faster | uv.lock (automatic) | Yes |

### Decision
**uv.** Rust-based, drop-in replacement for pip/virtualenv/poetry.
All commands: `uv run pytest`, `uv run alembic`, `uv run uvicorn`.
`uv.lock` is committed to git — reproducible builds.

---

## ADR-005 — JWT RS256 (asymmetric) over HS256

**Date:** 2025-05  
**Status:** Accepted

### Context
Single owner auth. JWT stored in httpOnly cookie.

### Options
| Algorithm | Key | Verify with |
|---|---|---|
| HS256 | 1 shared secret | Same secret (sign + verify) |
| RS256 | Private key (sign) + Public key (verify) | Only public key needed to verify |

### Decision
**RS256.** The public key can be shared with the NuxtJS server to verify tokens
without exposing the signing key. If the frontend is ever compromised, the
private key (on Railway only) is not at risk. Slight overhead is irrelevant
at this scale.

**Cookie flags:** `HttpOnly; Secure; SameSite=Strict` — not accessible to JS,
HTTPS only, CSRF protection.

---

## ADR-006 — Redis for cache, sessions, rate limits, alerts

**Date:** 2025-05  
**Status:** Accepted

### Context
Multiple Redis use-cases needed. Single Redis instance sufficient at this scale.

### Uses
| Use case | Key pattern | TTL |
|---|---|---|
| P&L cache (past months) | `pl:monthly:{month}` | 24h |
| JWT blocklist (logout) | `session:blocklist:{jti}` | 24h |
| Rate limiting | `ratelimit:{type}:{ip}` | 60s |
| Alert throttle | `alert:{type}:{id}` | 12h |
| Webhook idempotency | `webhook:rzp:{payment_id}` | 7 days |
| Order idempotency | `idem:order:{key}` | 24h |

### Decision
**Single Redis 7 instance.** All keys namespaced by environment prefix
(`local:`, `staging:`, `prod:`). If Redis is unavailable, operations degrade
gracefully — P&L recalculates, rate limits skip, alerts may double-send.

---

## ADR-007 — PostgreSQL row locking for stock decrement

**Date:** 2025-05  
**Status:** Accepted

### Context
Race condition: two customers order the last 5 kg simultaneously.
Both check stock (5 kg available), both see enough, both place orders.
Result: −5 kg stock. Physical impossibility.

### Options
| Approach | How | Issue |
|---|---|---|
| Application lock (Redis SETNX) | Lock per product, release after | Redis availability dependency |
| Optimistic locking (version column) | Retry on version mismatch | Retry logic complexity |
| Pessimistic locking (SELECT FOR UPDATE) | DB row lock inside transaction | Simple, guaranteed |

### Decision
**SELECT FOR UPDATE inside an atomic transaction.**

```python
# In InventoryRepository:
async def get_stock_locked(self, product_id):
    result = await self.db.execute(
        select(InventoryStock)
        .where(InventoryStock.product_id == product_id)
        .with_for_update()  # ← row lock
    )
    return result.scalar_one_or_none()
```

The lock is held only during the transaction (milliseconds). No other request
can read or modify that row until the transaction commits or rolls back.

---

## ADR-008 — Soft delete only for financial records

**Date:** 2025-05  
**Status:** Accepted

### Context
Income Tax / GST audit can look back 7 years. Hard-deleting financial records
is a legal risk. Accidentally deleted records are irrecoverable.

### Decision
**`deleted_at` timestamp only. Never `DELETE` from financial tables.**

Tables that must never hard-delete:
- `stock_entries` (financial ledger)
- `orders`, `order_items`, `payments`
- `farm_seasons`, `farm_inputs`, `farm_millings`
- `petha_batches`, `petha_batch_costs`
- `fixed_costs`, `assets`

To "correct" a stock entry: create a reversing entry, not edit/delete.

---

## ADR-009 — Fire-and-forget notifications

**Date:** 2025-05  
**Status:** Accepted

### Context
WhatsApp notifications (WATI) can fail. Should a failed notification fail the order?

### Decision
**No.** Notifications are `BackgroundTasks` registered after the DB transaction
commits. WATI failure is logged to Sentry but never propagates to the user.

```python
# After transaction:
bg.add_task(self.notify.order_confirmed, order)   # fire-and-forget
return order   # response sent regardless of notification status
```

The webhook must return 200 to Razorpay quickly. Notifications run after.

---

## ADR-010 — Single .env.local with absolute path resolution

**Date:** 2025-05  
**Status:** Accepted

### Context
`uv run alembic` and `uv run uvicorn` may run from different working directories.
`env_file=".env.local"` (relative path) fails when CWD is not `backend/`.

### Decision
Anchor env file path to `__file__` location:

```python
_BACKEND_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            str(_BACKEND_DIR / ".env"),
            str(_BACKEND_DIR / ".env.local"),
        ),
    )
```

This works regardless of whether the process is started from the repo root,
`backend/`, or anywhere else.