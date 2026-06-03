# Database Design

## Current implementation status

Verified in GitHub Codespaces on 2026-06-03:

| Area | Status | Notes |
|---|---|---|
| Local services | Working | `make up` starts local PostgreSQL and Redis/Valkey when Docker daemon is unavailable |
| Migrations | Working | `make migrate` applies `0001_initial` using async Alembic |
| Seed data | Working | `make seed` creates owner plus five default products |
| Health checks | Working | `/health` and `/health/ready` return OK/ready |
| Public catalog | Working | `GET /api/products/` returns active seeded products without login |
| Owner auth | Working | `POST /api/auth/login` sets an HttpOnly RS256 JWT cookie |

This document is the target database contract. The current initial migration creates tables from SQLAlchemy `Base.metadata`; future migrations should use explicit Alembic operations once the schema stabilizes.

---

## Design principles

| Principle | Rule |
|---|---|
| Money | `NUMERIC(15,5)` everywhere — never `FLOAT` or `DOUBLE` |
| Quantity | `NUMERIC(10,3)` — supports kg to 3 decimal places |
| Primary keys | UUID v4 — no sequential integer PKs (prevents enumeration) |
| Soft delete | `deleted_at TIMESTAMPTZ` — never `DELETE` on financial tables |
| Timestamps | All in UTC, `TIMESTAMPTZ` type |
| Naming | `snake_case`, tables = plural nouns, FK = `{table_singular}_id` |
| Constraints | CHECK constraints at DB level as last-resort guard |
| Indexes | Created explicitly — never rely on ORM auto-index |

---

## Type reference

```sql
-- Money: 15 digits total, 5 after decimal point
-- Max value: ₹9,999,999,999.99999  (9.9 billion rupees — enough headroom)
NUMERIC(15, 5)

-- Quantity: 10 digits total, 3 after decimal point
-- Supports: 0.001 kg (1 gram) to 9,999,999.000 kg
NUMERIC(10, 3)

-- UUIDs: stored as native PostgreSQL UUID (16 bytes, not 36-char string)
UUID

-- JSON blobs (recipe snapshots, config): native JSONB (binary, indexed)
JSONB

-- All timestamps: timezone-aware
TIMESTAMPTZ
```

---

## Complete table definitions

### owners
Single row for the shop owner. No multi-tenancy at this scale.

```sql
CREATE TABLE owners (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    username      VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,          -- bcrypt cost=12
    phone         VARCHAR(15),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_owners_username ON owners(username);
```

---

### products
Master product catalogue. Five SKUs currently.

```sql
CREATE TABLE products (
    id                   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    name                 VARCHAR(200) NOT NULL,
    slug                 VARCHAR(220) NOT NULL UNIQUE,   -- URL-safe, indexed
    category             VARCHAR(20)  NOT NULL,          -- 'rice' | 'petha'
    unit                 VARCHAR(10)  NOT NULL,          -- 'kg' | 'pc' | 'cup'

    -- Four-layer cost model
    sell_price           NUMERIC(15,5) NOT NULL CHECK (sell_price >= 0),
    farm_cost            NUMERIC(15,5) NOT NULL DEFAULT 0,
    labor_cost           NUMERIC(15,5) NOT NULL DEFAULT 0,
    overhead_cost        NUMERIC(15,5) NOT NULL DEFAULT 0,
    packaging_cost       NUMERIC(15,5) NOT NULL DEFAULT 0,
    normal_loss_percent  NUMERIC(5,2)  NOT NULL DEFAULT 0
                                       CHECK (normal_loss_percent >= 0
                                          AND normal_loss_percent < 100),

    -- Computed by application on every create/update (not DB generated)
    -- Formula: farm+labor+overhead+packaging + loss_absorption
    true_cost            NUMERIC(15,5) NOT NULL DEFAULT 0,

    is_own_farm          BOOLEAN      NOT NULL DEFAULT TRUE,
    is_active            BOOLEAN      NOT NULL DEFAULT TRUE,
    low_stock_threshold  NUMERIC(10,3) NOT NULL DEFAULT 5,
    image_url            VARCHAR(500),
    description          TEXT,

    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at           TIMESTAMPTZ              -- soft delete
);

CREATE UNIQUE INDEX uq_products_slug    ON products(slug);
CREATE INDEX        ix_products_active  ON products(is_active)
    WHERE deleted_at IS NULL;             -- partial index — only active rows
CREATE INDEX        ix_products_category ON products(category);
```

**Notes:**
- `true_cost` is updated by the service layer on every cost field change
- `slug` is auto-generated from `name` by the service (slugify function)
- `deleted_at IS NOT NULL` means hidden from public shop and owner can still see it

---

### inventory_stock
Current live stock level. One row per product. Updated on every stock movement.

```sql
CREATE TABLE inventory_stock (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id  UUID        NOT NULL UNIQUE REFERENCES products(id),
    current_qty NUMERIC(10,3) NOT NULL DEFAULT 0
                            CHECK (current_qty >= 0),    -- stock can never go negative
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_inventory_stock_product ON inventory_stock(product_id);
```

**Notes:**
- One row per product — enforced by UNIQUE constraint
- `SELECT FOR UPDATE` used during order confirmation to prevent race conditions
- `CHECK (current_qty >= 0)` is the database-level safety net
- Updated atomically with every order confirm and stock entry

---

### stock_entries
**The financial ledger.** Every stock movement ever. Never delete.
This is the source of truth for P&L calculation.

```sql
CREATE TABLE stock_entries (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key  UUID        NOT NULL UNIQUE,   -- prevents duplicate entries
    product_id       UUID        NOT NULL REFERENCES products(id),

    entry_type       VARCHAR(30) NOT NULL,
    -- Allowed values:
    -- 'sale'             — sold to customer
    -- 'purchase'         — bought externally
    -- 'wastage_normal'   — expected milling loss (absorbed into COGS)
    -- 'wastage_abnormal' — unexpected loss (separate P&L line)
    -- 'consumption'      — owner personal use at market price
    -- 'opening_stock'    — period-start balance
    -- 'closing_stock'    — period-end balance
    -- 'production'       — from milling or petha batch
    -- 'capex'            — asset purchase (not an expense)
    -- 'fixed_cost'       — recurring operational cost
    -- 'provision'        — accrued liability (e.g. working capital interest)

    qty              NUMERIC(10,3) NOT NULL CHECK (qty > 0),  -- always positive
    unit_cost        NUMERIC(15,5),            -- actual unit cost at entry time
    total_amount     NUMERIC(15,5) NOT NULL,   -- qty × unit_cost (or explicit)

    -- Variance analysis (actual vs standard)
    standard_unit_cost NUMERIC(15,5),         -- products.true_cost at entry time
    price_variance     NUMERIC(15,5),         -- (actual_sell − standard_sell) × qty
    cost_variance      NUMERIC(15,5),         -- (actual_buy − standard_cost) × qty

    -- Classification
    source          VARCHAR(20),   -- 'own' | 'external' | 'internal'
    channel         VARCHAR(20),   -- 'online' | 'offline'
    pay_mode        VARCHAR(20),   -- 'cash' | 'upi_manual' | 'razorpay' | 'credit'
    wastage_type    VARCHAR(20),   -- 'normal' | 'abnormal'

    -- Traceability
    reference_id    UUID,          -- order_id | season_id | batch_id
    reference_type  VARCHAR(50),   -- 'order' | 'season' | 'petha_batch' | 'manual'
    date            DATE NOT NULL, -- business date (may differ from created_at)
    note            TEXT,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ            -- soft delete: use reverse entry to correct
);

-- Indexes for P&L query performance (fetch all entries for a month)
CREATE INDEX ix_entries_date         ON stock_entries(date);
CREATE INDEX ix_entries_type         ON stock_entries(entry_type);
CREATE INDEX ix_entries_product      ON stock_entries(product_id);
CREATE INDEX ix_entries_date_type    ON stock_entries(date, entry_type);
CREATE INDEX ix_entries_reference    ON stock_entries(reference_id)
    WHERE reference_id IS NOT NULL;
CREATE UNIQUE INDEX uq_entries_idem  ON stock_entries(idempotency_key);

-- Partial index for P&L calculation (most common query)
CREATE INDEX ix_entries_active_date  ON stock_entries(date, entry_type)
    WHERE deleted_at IS NULL;
```

**Why qty is always positive:**
Direction is determined by `entry_type`, not sign.
`sale` of 3 kg and `purchase` of 3 kg both have `qty=3`.
This makes aggregation simpler and prevents sign errors.

---

### monthly_stock
Opening and closing stock values per product per month.
Required for accurate COGS calculation.

```sql
CREATE TABLE monthly_stock (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id  UUID        NOT NULL REFERENCES products(id),
    month       CHAR(7)     NOT NULL,   -- 'YYYY-MM' format e.g. '2025-05'
    stock_type  VARCHAR(10) NOT NULL,   -- 'opening' | 'closing'
    qty         NUMERIC(10,3) NOT NULL,
    value       NUMERIC(15,5) NOT NULL, -- qty × unit_cost at that date
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_monthly_stock UNIQUE (product_id, month, stock_type)
);

CREATE INDEX ix_monthly_stock_month   ON monthly_stock(month);
CREATE INDEX ix_monthly_stock_product ON monthly_stock(product_id, month);
```

**Notes:**
- Owner enters these manually at start and end of each month
- Missing opening stock triggers a warning in P&L (not an error)
- `value` = physical count × weighted average cost

---

### orders
One row per customer order. Parent of order_items and payments.

```sql
CREATE TABLE orders (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key  UUID        NOT NULL UNIQUE,
    order_number     VARCHAR(20) NOT NULL UNIQUE,  -- 'LKP-2025-0042'

    customer_name    VARCHAR(200) NOT NULL,
    customer_phone   VARCHAR(15)  NOT NULL,
    customer_address TEXT,                         -- required if delivery

    fulfillment_type VARCHAR(20) NOT NULL,   -- 'pickup' | 'delivery'
    channel          VARCHAR(20) NOT NULL,   -- 'online' | 'offline'
    status           VARCHAR(30) NOT NULL DEFAULT 'pending',

    total_amount     NUMERIC(15,5) NOT NULL,  -- before discount
    discount_amount  NUMERIC(15,5) NOT NULL DEFAULT 0,
    final_amount     NUMERIC(15,5) NOT NULL,  -- total - discount

    razorpay_order_id VARCHAR(100),           -- from Razorpay API
    cancel_reason    TEXT,

    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at       TIMESTAMPTZ
);

CREATE UNIQUE INDEX uq_orders_idem        ON orders(idempotency_key);
CREATE UNIQUE INDEX uq_orders_number      ON orders(order_number);
CREATE INDEX        ix_orders_status      ON orders(status);
CREATE INDEX        ix_orders_channel     ON orders(channel);
CREATE INDEX        ix_orders_created     ON orders(created_at DESC);
CREATE INDEX        ix_orders_phone       ON orders(customer_phone);
-- Dashboard filter: status + channel
CREATE INDEX        ix_orders_status_chan ON orders(status, channel)
    WHERE deleted_at IS NULL;
```

---

### order_items
Line items for each order. Prices are **snapshots** — frozen at order time.

```sql
CREATE TABLE order_items (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id     UUID        NOT NULL REFERENCES orders(id),
    product_id   UUID        NOT NULL REFERENCES products(id),

    -- SNAPSHOT fields — product price changes do not affect existing orders
    product_name VARCHAR(200) NOT NULL,
    unit_price   NUMERIC(15,5) NOT NULL,   -- sell_price at order time

    qty          NUMERIC(10,3) NOT NULL CHECK (qty > 0),
    total        NUMERIC(15,5) NOT NULL,   -- qty × unit_price
    source       VARCHAR(20)  NOT NULL DEFAULT 'own'  -- 'own' | 'bought'
);

CREATE INDEX ix_order_items_order   ON order_items(order_id);
CREATE INDEX ix_order_items_product ON order_items(product_id);
```

---

### payments
One payment record per order. Tracks Razorpay and manual payments.

```sql
CREATE TABLE payments (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id            UUID        NOT NULL UNIQUE REFERENCES orders(id),

    payment_mode        VARCHAR(30) NOT NULL,
    -- 'razorpay' | 'cash' | 'upi_manual' | 'credit'

    status              VARCHAR(30) NOT NULL DEFAULT 'pending',
    -- 'pending' | 'paid' | 'failed' | 'outstanding' | 'refunded'

    amount              NUMERIC(15,5) NOT NULL,

    -- Razorpay-specific (null for cash/UPI manual)
    razorpay_order_id   VARCHAR(100),
    razorpay_payment_id VARCHAR(100) UNIQUE,   -- idempotency: duplicate webhooks check
    razorpay_signature  VARCHAR(300),

    credit_due_date     TIMESTAMPTZ,           -- when credit payment is expected
    paid_at             TIMESTAMPTZ,
    refunded_at         TIMESTAMPTZ,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_payments_order  ON payments(order_id);
CREATE UNIQUE INDEX uq_payments_rzp_id ON payments(razorpay_payment_id)
    WHERE razorpay_payment_id IS NOT NULL;   -- partial: only non-null values
CREATE INDEX        ix_payments_status ON payments(status);
CREATE INDEX        ix_payments_due    ON payments(credit_due_date)
    WHERE status = 'outstanding';            -- outstanding credits dashboard
```

---

### farm_seasons
One row per planting season. Tracks cultivation through milling.

```sql
CREATE TABLE farm_seasons (
    id                     UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    variety                VARCHAR(30) NOT NULL,   -- 'joha'|'bora_saul'|'kali_jeera'
    area_bigha             NUMERIC(8,2) NOT NULL,
    status                 VARCHAR(20) NOT NULL DEFAULT 'active',
    -- 'planning'|'active'|'harvested'|'milled'|'complete'|'failed'

    start_date             DATE        NOT NULL,
    harvest_date           DATE,

    -- Filled after harvest
    dhan_qty_kg            NUMERIC(10,3),

    -- Filled after milling
    chawl_qty_kg           NUMERIC(10,3),
    total_cultivation_cost NUMERIC(15,5),
    milling_yield_percent  NUMERIC(5,2),

    -- Computed costs (filled by service after milling)
    cost_per_kg_dhan       NUMERIC(15,5),
    cost_per_kg_chawl      NUMERIC(15,5),
    transfer_price_per_kg  NUMERIC(15,5),   -- cost_per_kg_chawl × 1.12

    notes                  TEXT,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_farm_seasons_status  ON farm_seasons(status);
CREATE INDEX ix_farm_seasons_variety ON farm_seasons(variety);
```

---

### farm_inputs
Individual cultivation cost entries for a season.

```sql
CREATE TABLE farm_inputs (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    season_id    UUID        NOT NULL REFERENCES farm_seasons(id),
    input_type   VARCHAR(30) NOT NULL,
    -- 'seed'|'fertilizer'|'pesticide'|'labor'|'irrigation'|'transport'|'other'
    description  TEXT        NOT NULL,
    qty          NUMERIC(10,3),
    unit         VARCHAR(20),            -- 'kg'|'litre'|'hr'|'trip'
    unit_cost    NUMERIC(15,5) NOT NULL,
    total_amount NUMERIC(15,5) NOT NULL,
    date         DATE        NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_farm_inputs_season ON farm_inputs(season_id);
```

---

### farm_millings
Milling records for a season. Includes by-product recovery.

```sql
CREATE TABLE farm_millings (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    season_id           UUID        NOT NULL REFERENCES farm_seasons(id),
    dhan_sent_kg        NUMERIC(10,3) NOT NULL,
    chawl_received_kg   NUMERIC(10,3) NOT NULL,
    husk_recovered_kg   NUMERIC(10,3) NOT NULL DEFAULT 0,
    bran_recovered_kg   NUMERIC(10,3) NOT NULL DEFAULT 0,
    broken_rice_kg      NUMERIC(10,3) NOT NULL DEFAULT 0,
    milling_charges     NUMERIC(15,5) NOT NULL,

    -- By-product market prices at milling time
    husk_market_price   NUMERIC(15,5) NOT NULL DEFAULT 0,
    bran_market_price   NUMERIC(15,5) NOT NULL DEFAULT 0,
    broken_market_price NUMERIC(15,5) NOT NULL DEFAULT 0,

    yield_percent       NUMERIC(5,2),   -- chawl / dhan × 100
    milling_date        DATE NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_farm_millings_season ON farm_millings(season_id);
```

---

### petha_batches
One production batch per row. Tracks from mixing to expiry.

```sql
CREATE TABLE petha_batches (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    variety              VARCHAR(20) NOT NULL,    -- 'septa' | 'narikal'
    status               VARCHAR(20) NOT NULL DEFAULT 'in_production',
    -- 'in_production' | 'completed' | 'expired'

    batch_date           DATE        NOT NULL,
    planned_pieces       INTEGER     NOT NULL CHECK (planned_pieces > 0),
    good_pieces          INTEGER,               -- filled on completion
    rejected_pieces      INTEGER,               -- filled on completion

    -- Cost breakdown by type
    total_ingredient_cost NUMERIC(15,5) NOT NULL DEFAULT 0,
    total_labor_cost      NUMERIC(15,5) NOT NULL DEFAULT 0,
    total_overhead_cost   NUMERIC(15,5) NOT NULL DEFAULT 0,
    total_batch_cost      NUMERIC(15,5) NOT NULL DEFAULT 0,  -- sum of above

    -- Filled on completion (absorption costing)
    cost_per_piece       NUMERIC(15,5),   -- total_batch_cost / good_pieces

    shelf_life_days      INTEGER NOT NULL DEFAULT 7,
    expiry_date          DATE    NOT NULL,              -- batch_date + shelf_life_days

    recipe_snapshot      JSONB   NOT NULL DEFAULT '{}', -- frozen at batch creation
    abnormal_loss_amount NUMERIC(15,5),                 -- set on expiry

    notes                TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_petha_batches_status  ON petha_batches(status);
CREATE INDEX ix_petha_batches_expiry  ON petha_batches(expiry_date)
    WHERE status = 'completed';   -- expiry dashboard only needs active batches
CREATE INDEX ix_petha_batches_variety ON petha_batches(variety);
```

---

### petha_batch_costs
Individual cost lines for a petha batch.

```sql
CREATE TABLE petha_batch_costs (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id     UUID        NOT NULL REFERENCES petha_batches(id),
    cost_type    VARCHAR(20) NOT NULL,   -- 'ingredient'|'labor'|'fuel'|'overhead'
    description  TEXT        NOT NULL,
    qty          NUMERIC(10,3),
    unit_cost    NUMERIC(15,5) NOT NULL,
    total_amount NUMERIC(15,5) NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_batch_costs_batch ON petha_batch_costs(batch_id);
```

---

### fixed_costs
Recurring monthly costs (stall rent, transport, etc.).

```sql
CREATE TABLE fixed_costs (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name           VARCHAR(200) NOT NULL,
    category       VARCHAR(50) NOT NULL,
    -- 'stall'|'fuel'|'transport'|'drawing'|'provision'|'misc'
    monthly_amount NUMERIC(15,5) NOT NULL CHECK (monthly_amount >= 0),
    is_active      BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at     TIMESTAMPTZ
);

CREATE INDEX ix_fixed_costs_active ON fixed_costs(is_active)
    WHERE deleted_at IS NULL;
```

---

### assets
Capital assets for depreciation calculation.

```sql
CREATE TABLE assets (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name                 VARCHAR(200) NOT NULL,
    cost                 NUMERIC(15,5) NOT NULL CHECK (cost > 0),
    useful_life_years    INTEGER     NOT NULL CHECK (useful_life_years > 0),

    -- Computed by application: cost / (useful_life_years × 12)
    monthly_depreciation NUMERIC(15,5) NOT NULL,

    purchase_date        DATE        NOT NULL,
    is_active            BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at           TIMESTAMPTZ
);

CREATE INDEX ix_assets_active ON assets(is_active) WHERE deleted_at IS NULL;
```

---

### notifications
Audit log of every WhatsApp message sent.

```sql
CREATE TABLE notifications (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    recipient_phone VARCHAR(15) NOT NULL,
    recipient_type VARCHAR(20) NOT NULL,    -- 'owner' | 'customer'
    channel        VARCHAR(20) NOT NULL,    -- 'whatsapp' | 'sms'
    template_name  VARCHAR(100) NOT NULL,
    message_body   TEXT,
    status         VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- 'pending' | 'sent' | 'failed'
    reference_id   UUID,                   -- order_id that triggered this
    reference_type VARCHAR(50),
    sent_at        TIMESTAMPTZ,
    error_message  TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_notifications_status    ON notifications(status);
CREATE INDEX ix_notifications_reference ON notifications(reference_id)
    WHERE reference_id IS NOT NULL;
CREATE INDEX ix_notifications_created   ON notifications(created_at DESC);
```

---

## Relationships summary

```
products (1) ──────── (N) inventory_stock   [one live stock row per product]
products (1) ──────── (N) stock_entries     [all movements]
products (1) ──────── (N) monthly_stock     [opening/closing per month]
products (1) ──────── (N) order_items       [sold in orders]

orders   (1) ──────── (N) order_items       [line items]
orders   (1) ──────── (1) payments          [one payment per order]

farm_seasons (1) ──── (N) farm_inputs       [cultivation costs]
farm_seasons (1) ──── (N) farm_millings     [milling records]

petha_batches (1) ─── (N) petha_batch_costs [cost lines]
```

---

## Migration strategy

**Tool:** Alembic with async SQLAlchemy engine. Migrations are run explicitly with Makefile targets; FastAPI startup does not run migrations automatically.

```bash
# Generate migration from model changes
make revision MSG="add product description field"

# Apply migrations
make migrate

# Roll back one step
make rollback
```

**Rules:**
1. Never edit a migration after it has been applied to staging or production
2. Never drop a column — add `deleted_at`, then stop using old column
3. Data migrations go in separate numbered migration files
4. Every migration must have a working `downgrade()` function

**Naming convention:**
```
migrations/versions/
  0001_initial.py
  0002_add_product_description.py
  0003_add_farm_millings_byproduct_prices.py
```

---

## Performance considerations

### N+1 query prevention
Always use `selectinload` for relationships loaded in list endpoints:

```python
# ✅ One query for orders + one batch query for all items
select(Order).options(
    selectinload(Order.items),
    selectinload(Order.payment),
)

# ❌ N+1: one query per order for items
orders = await db.execute(select(Order))
for order in orders:
    items = order.items  # triggers N separate queries
```

### P&L query optimisation
The monthly P&L fetches all entries for a month in one CTE query:

```sql
SELECT * FROM stock_entries
WHERE date BETWEEN '2025-05-01' AND '2025-05-31'
  AND deleted_at IS NULL;
-- Uses ix_entries_active_date index
```

### Index coverage
Every common filter and join column has an index.
Partial indexes (e.g., `WHERE deleted_at IS NULL`) avoid indexing deleted rows.

---

## Data retention policy

| Table | Minimum retention | Reason |
|---|---|---|
| `stock_entries` | 7 years | Income Tax audit requirement |
| `orders`, `payments` | 7 years | GST audit requirement |
| `farm_seasons` | 7 years | Financial records |
| `petha_batches` | 7 years | Financial records |
| `notifications` | 1 year | Dispute resolution |
| `owners` | Forever | System integrity |
| `products` | Forever (soft delete) | Reference in old orders |

**Implementation:** `deleted_at` is set on "delete" — records are never physically removed.
Annual archival to cold storage (S3/R2) after the active window is future work.
