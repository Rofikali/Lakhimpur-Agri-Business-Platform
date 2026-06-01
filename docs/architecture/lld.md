# Low Level Design (LLD)

## Module structure

Every module follows the same four-file pattern. No exceptions.

```
modules/{name}/
├── models.py      SQLAlchemy ORM models (DB tables)
├── schemas.py     Pydantic request/response models
├── repository.py  DB queries only — no business logic
├── service.py     Business logic only — no SQL, no HTTP
└── router.py      HTTP interface only — no business logic
```

**Seam rule:** modules never import each other's `repository.py` directly.
Cross-module data access goes through the other module's `service.py`.
This keeps the boundary clean for future microservice extraction.

---

## Design patterns used

### 1. Repository pattern
Separates data access from business logic. Every DB query lives in `repository.py`.
Services never write raw SQL or call `db.execute()` directly.

```python
# ✅ correct — service calls repository
class OrderService:
    async def get_order(self, order_id): 
        return await self.repo.get(order_id)  # repo does the SQL

# ❌ wrong — service writes SQL
class OrderService:
    async def get_order(self, order_id):
        return await self.db.execute(select(Order).where(...))
```

### 2. Dependency injection (FastAPI Depends)
Service factories are registered in `core/dependencies.py`.
Routers declare what they need via `Depends()` — never instantiate services directly.

```python
# router.py
@router.post("/")
async def create_order(
    body    : OrderCreate,
    service : OrderService = Depends(get_order_service),  # injected
):
    return await service.create_order(body)
```

### 3. Unit of work (SQLAlchemy session)
Each HTTP request gets one `AsyncSession`. All DB operations in that request
share the session. The session is committed or rolled back atomically.
For critical operations (confirm order + decrement stock), an explicit nested
transaction is used:

```python
async with self.repo.transaction():   # begin_nested()
    order.status = "confirmed"
    await self.repo.save(order)
    for item in order.items:
        await self.inventory.decrement_stock(...)  # SELECT FOR UPDATE inside
# COMMIT here — atomic
```

### 4. Strategy pattern (P&L calculator)
The P&L calculator is a pure function — no DB access, no side effects.
The service fetches all data, passes it to the calculator, caches the result.
This makes the calculation independently testable with no DB fixtures.

```python
# service.py fetches data
entries, stocks, assets, products = await self._fetch_all(month)

# calculator.py is pure
result = calculate(month, entries, stocks, assets, products)

# service.py caches result
await cache_set(key, result.to_dict(), ttl=86400)
```

### 5. Idempotency pattern
All mutation endpoints accept an `idempotency_key` (UUID from client).
The first call creates the resource. Subsequent calls with the same key
return the already-created resource without side effects.

```python
existing = await self.repo.find_by_idempotency_key(data.idempotency_key)
if existing:
    return self.repo.to_dict(existing)   # return same result, no duplicate
```

Used in: orders, stock entries, webhook processing.

### 6. Observer pattern (fire-and-forget notifications)
Notifications are BackgroundTasks — registered after the DB transaction commits.
If WATI fails, the order is unaffected. Failure is logged only.

```python
# After transaction commits:
bg.add_task(self.notify.order_confirmed, order)   # non-blocking
bg.add_task(self.notify.new_order_to_owner, order)
return order   # response sent immediately
```

### 7. Absorption costing pattern (petha batches)
Rejected pieces' cost is absorbed by good pieces — a standard manufacturing
accounting technique. This is not a "pattern" in the GoF sense but a business
logic pattern enforced consistently:

```python
cost_per_piece = total_batch_cost / good_pieces  # rejected absorbed
# If good_pieces = 0: all cost → abnormal_loss (not cost_per_piece)
```

---

## Module dependency graph

```
auth ──────────────────────────────────────────── (no deps)
products ─────────────────────────────────────── (no deps)
inventory ────────────── depends on → products
orders ───────────────── depends on → products, inventory, payments, notify
pl_engine ───────────── depends on → inventory (reads stock_entries)
farm ────────────────── depends on → inventory (transfers chawl to stock)
petha ───────────────── depends on → inventory, products
notify ──────────────── (external: WATI API only)
payments ────────────── (external: Razorpay API only)
finance ─────────────── (standalone: FixedCost, Asset)
```

Future split path: replace service imports with HTTP calls between services.
The interface (method signatures) stays unchanged.

---

## State machines

### Order states

```
         ┌──────────┐
    ●───▶│ pending  │──────────────────────────────────────┐
         └────┬─────┘                                       │
    (payment ok / offline)                                  │
         ┌────▼─────┐                                       │
         │confirmed │───────────────────────────────────────┤
         └────┬─────┘                                       │
    (owner)   │                                             │
         ┌────▼─────┐                                       │ cancelled
         │  packed  │───────────────────────────────────────┤
         └──┬──┬────┘                                       │
   delivery │  │ pickup                                     │
       ┌────▼┐ └──────────────────┐                         │
       │o4d  │              ┌─────▼────┐                    │
       └──┬──┘              │picked_up │────────────────────┤
    ┌─────▼────┐            └─────┬────┘                    │
    │delivered │                  │                         │
    └─────┬────┘            ┌─────▼────┐                    │
          └────────────────▶│completed │◀───────────────────┘
                             └──────────┘        ↑
                                          ┌──────────┐
                                          │cancelled │◀── from any non-completed
                                          └──────────┘     (restores stock if confirmed/packed)
```

### Farm season states

```
planning ──▶ active ──▶ harvested ──▶ milled ──▶ complete
    │           │           │           │
    └───────────┴───────────┴───────────┴──▶ failed
                                              (all cost = abnormal loss)
```

### Petha batch states

```
in_production ──▶ completed ──▶ sold_out (●)
                      │
                      └──▶ expired ──▶ abnormal_loss recorded
```

### Payment states

```
pending ──▶ paid (●)
   │
   ├──▶ failed
   │
   ├──▶ outstanding ──▶ collected (●)
   │
   └──▶ (paid) ──▶ refunded
```

---

## Key algorithms

### P&L engine

```python
# COGS formula
cogs_total = (
    cogs_opening       # opening stock value
  + cogs_own_prod      # own-farm sales × farm_cost per unit
  + cogs_purchased     # external purchases at actual cost
  + cogs_norm_loss     # normal milling loss (absorbed, not a P&L loss)
  + cogs_consumed      # own consumption at market price
  - cogs_closing       # closing stock value
)

gross_profit = rev_total - cogs_total
net_profit   = gross_profit - abnormal_loss - opex_total
```

### Normal loss absorption

```python
# To get 1 kg chawl from dhan with 33% loss:
# Need 1 / (1 - 0.33) = 1.4925 kg dhan
loss_pct    = normal_loss_percent / 100
loss_absorb = farm_cost × loss_pct / (1 - loss_pct)
true_cost   = farm_cost + loss_absorb + labor + overhead + packaging
```

### Milling yield and byproduct credit

```python
yield_pct          = chawl_received / dhan_sent × 100
byproduct_revenue  = husk_kg×husk_price + bran_kg×bran_price + broken_kg×broken_price
net_cost           = (cultivation_cost + milling_charges) - byproduct_revenue
cost_per_kg_chawl  = net_cost / chawl_received
transfer_price     = cost_per_kg_chawl × 1.12   # 12% inter-segment markup
```

### Batch cost absorption

```python
total_batch_cost = ingredient + labor + overhead
cost_per_piece   = total_batch_cost / good_pieces   # rejected absorbed
rejection_pct    = rejected_pieces / planned_pieces × 100
# If good_pieces = 0:
#   cost_per_piece = 0
#   abnormal_loss  = total_batch_cost
```

---

## Pydantic schema conventions

```python
# Money input: reject float, accept string or Decimal
@field_validator("sell_price", mode="before")
@classmethod
def no_float(cls, v):
    if isinstance(v, float):
        raise ValueError("Use string or Decimal — never float")
    return Decimal(str(v))

# Money output: always string (5 decimal places)
@field_validator("sell_price", mode="before")
@classmethod
def to_str(cls, v):
    return str(v)  # "105.00000"

# Response models always use from_attributes=True
class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
```

---

## Cache design

### Key naming convention

```
{env}:{module}:{resource}:{identifier}

prod:pl:monthly:2025-05
prod:products:list:active
prod:products:stock:joha-rice
prod:session:blocklist:{jti}
prod:ratelimit:api:{ip}
prod:alert:low_stock:{product_slug}
prod:idem:order:{uuid}
prod:webhook:rzp:{razorpay_payment_id}
```

### TTL table

| Key pattern | TTL | Invalidation trigger |
|---|---|---|
| `pl:monthly:{past_month}` | 24h | Never (past is immutable) |
| `pl:monthly:{current_month}` | No cache | Always recalculate |
| `products:list:active` | 5 min | Product create/update/delete |
| `products:stock:{slug}` | 30 sec | Every stock movement |
| `session:blocklist:{jti}` | 24h | Auto-expire (JWT lifetime) |
| `ratelimit:api:{ip}` | 60s | Auto-expire |
| `ratelimit:login:{ip}` | 60s | Auto-expire |
| `alert:low_stock:{slug}` | 12h | Prevents alert spam |
| `idem:order:{key}` | 24h | Auto-expire |
| `webhook:rzp:{payment_id}` | 7 days | Auto-expire |

---

## Error response standard

Every error returns the same shape:

```json
{
  "error":      "STOCK_INSUFFICIENT",
  "message":    "Only 3.5kg available for Joha Rice",
  "field":      "quantity",
  "detail":     { "available_qty": "3.500", "requested_qty": "5.000" },
  "status":     422,
  "request_id": "abc123-xyz789"
}
```

`error` is machine-readable and stable across versions.
`message` is human-readable and may change.
`request_id` is the X-Request-ID header value — share when reporting bugs.